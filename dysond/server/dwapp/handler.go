package dwapp

import (
	"bufio"
	"bytes"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/http/httputil"
	"net/url"
	"regexp"
	"strconv"
	"strings"

	"github.com/cosmos/cosmos-sdk/client"

	scriptv1 "dysonprotocol.com/x/script/types"
)

const (
	txtScriptNameRecordKey    = "DYSON_SCRIPT_NAME"
	txtScriptAddressRecordKey = "DYSON_SCRIPT_ADDRESS"
)

// DysonTxtRecords holds the parsed TXT record values for Dyson script configuration
type DysonTxtRecords struct {
	ScriptName    string
	ScriptAddress string
}

func NewDefaultHandler(clientCtx client.Context, ScriptAddressOrNamePattern string, publicHostTemplate string, bootstrapPeers []string) http.Handler {
	scriptAddressOrNameRe := regexp.MustCompile(ScriptAddressOrNamePattern)
	h := &DefaultHandler{
		clientCtx:             clientCtx,
		scriptAddressOrNameRe: scriptAddressOrNameRe,
		publicHostTemplate:    publicHostTemplate,
		bootstrapPeers:        bootstrapPeers,
	}

	// Initialize RPC reverse proxy from client context NodeURI
	upstream := strings.TrimSpace(clientCtx.NodeURI)
	if upstream != "" {
		if strings.HasPrefix(upstream, "tcp://") {
			upstream = "http://" + strings.TrimPrefix(upstream, "tcp://")
		} else if !strings.Contains(upstream, "://") {
			upstream = "http://" + upstream
		}
		if u, err := url.Parse(upstream); err == nil {
			proxy := httputil.NewSingleHostReverseProxy(u)
			origDirector := proxy.Director
			proxy.Director = func(r *http.Request) {
				origDirector(r)
				// preserve upstream host for proper routing and websockets
				r.Host = u.Host
				// trim the /rpc prefix so /rpc/abci_info -> /abci_info
				if strings.HasPrefix(r.URL.Path, "/rpc") {
					r.URL.Path = strings.TrimPrefix(r.URL.Path, "/rpc")
					if r.URL.Path == "" {
						r.URL.Path = "/"
					}
				}
			}
			proxy.ErrorHandler = func(rw http.ResponseWriter, r *http.Request, err error) {
				http.Error(rw, fmt.Sprintf("rpc proxy error: %v", err), http.StatusBadGateway)
			}
			h.rpcProxy = proxy
		}
	}

	return h
}

type DefaultHandler struct {
	clientCtx             client.Context
	scriptAddressOrNameRe *regexp.Regexp
	publicHostTemplate    string
	// RPC reverse proxy
	rpcProxy *httputil.ReverseProxy
	// Optional embedded libp2p service
	p2p *P2PService
	// Bootstrap peers for mesh networking
	bootstrapPeers []string
}

// SetP2PService attaches the libp2p service so HTTP handlers can expose bootstrap info.
func (h *DefaultHandler) SetP2PService(svc *P2PService) {
	h.p2p = svc
}

func (h *DefaultHandler) ServeHTTP(w http.ResponseWriter, req *http.Request) {
	// Reverse-proxy CometBFT RPC under /rpc/* to the configured NodeURI
	if strings.HasPrefix(req.URL.Path, "/rpc") {
		if h.rpcProxy == nil {
			http.Error(w, "rpc proxy not configured", http.StatusBadGateway)
			return
		}
		h.rpcProxy.ServeHTTP(w, req)
		return
	}

	// Bootstrap endpoint for libp2p connectivity (same-origin, no CORS required)
	if req.Method == http.MethodGet && req.URL.Path == "/libp2p/bootstrap" {
		if h.p2p == nil {
			http.Error(w, "libp2p disabled", http.StatusServiceUnavailable)
			return
		}
		if err := h.p2p.EnsurePubSub(req.Context(), h.clientCtx); err != nil {
			http.Error(w, fmt.Sprintf("libp2p pubsub init failed: %v", err), http.StatusInternalServerError)
			return
		}

		peerID := ""
		addrs := []string{}
		relayListenAddrs := []string{}
		if info := h.p2p.HostInfo(); info != nil {
			peerID = info.PeerID
			addrs = info.Addrs
			for _, addr := range addrs {
				if isBrowserDialable(addr) {
					relayListenAddrs = append(relayListenAddrs, fmt.Sprintf("%s/p2p-circuit", addr))
				}
			}
		}

		chainID := strings.TrimSpace(h.clientCtx.ChainID)
		resp := map[string]any{
			"peerId":           peerID,
			"addrs":            addrs,
			"relayListenAddrs": relayListenAddrs,
			"chainId":          chainID,
			"bootstrapPeers":   h.bootstrapPeers,
			"ice": map[string]any{
				"servers": []map[string]any{
					{"urls": []string{"stun:stun.l.google.com:19302"}},
					{"urls": []string{"stun:stun1.l.google.com:19302"}},
				},
			},
			"topicPrefix": "/" + chainID + "/v1/",
			"version":     "1",
		}
		w.Header().Set("Content-Type", "application/json; charset=utf-8")
		if err := json.NewEncoder(w).Encode(resp); err != nil {
			http.Error(w, fmt.Sprintf("bootstrap encode error: %v", err), http.StatusInternalServerError)
		}
		return
	}

	// POST /libp2p/verify: validate a single ADR-36 frame against a topic (utility)
	if req.Method == http.MethodPost && req.URL.Path == "/libp2p/verify" {
		type body struct {
			Topic  string `json:"topic"`
			TxJSON string `json:"adr36_tx_json"`
		}
		var b body
		if err := json.NewDecoder(req.Body).Decode(&b); err != nil {
			http.Error(w, fmt.Sprintf("invalid json: %v", err), http.StatusBadRequest)
			return
		}
		if h.p2p == nil {
			http.Error(w, "libp2p disabled", http.StatusServiceUnavailable)
			return
		}
		signer, payload, err := h.p2p.VerifyAndExtract(req.Context(), h.clientCtx, strings.TrimSpace(b.Topic), "", b.TxJSON)
		if err != nil {
			http.Error(w, err.Error(), http.StatusUnauthorized)
			return
		}
		var payloadObj any
		if err := json.Unmarshal([]byte(payload), &payloadObj); err != nil {
			payloadObj = json.RawMessage(payload)
		}
		w.Header().Set("Content-Type", "application/json; charset=utf-8")
		_ = json.NewEncoder(w).Encode(map[string]any{"signer": signer, "payload": payloadObj})
		return
	}

	// Auto-join via GossipSub tracer; no HTTP subscribe/unsubscribe endpoints

	// New endpoint: /redirect-to-dwapp/{address_or_name} -> redirect or return public host
	if strings.HasPrefix(req.URL.Path, "/redirect-to-dwapp/") {
		// Extract the address_or_name (first path segment) and preserve the rest of the path
		pathAfter := strings.TrimPrefix(req.URL.Path, "/redirect-to-dwapp/")
		pathAfter = strings.TrimLeft(pathAfter, "/")
		if pathAfter == "" {
			http.Error(w, "missing address_or_name", http.StatusBadRequest)
			return
		}

		segments := strings.SplitN(pathAfter, "/", 2)
		id := strings.TrimSpace(segments[0])
		restPath := ""
		if len(segments) == 2 {
			restPath = "/" + segments[1]
		}

		// Accept either a name ending in .dys or a dys21... address
		idLower := strings.ToLower(id)
		publicID := ""
		if strings.HasSuffix(idLower, ".dys") {
			publicID = strings.TrimSuffix(idLower, ".dys")
		} else if strings.HasPrefix(idLower, "dys2") {
			publicID = idLower
		} else {
			http.Error(w, "address_or_name must end with .dys or be a dys2… address", http.StatusBadRequest)
			return
		}

		// Map back to public host using template
		publicHost := strings.ReplaceAll(h.publicHostTemplate, "{address_or_name}", publicID)
		// 307 redirect to //{publicHost}{restPath}[?query] (relative protocol to all https or http)
		target := "//" + publicHost + restPath
		if req.URL.RawQuery != "" {
			target += "?" + req.URL.RawQuery
		}
		http.Redirect(w, req, target, http.StatusTemporaryRedirect)
		return
	}

	// get the raw request
	rawRequest, err := getRawRequest(req)
	if err != nil {
		http.Error(w, "Error getting raw request", http.StatusInternalServerError)
		return
	}

	// Create the request - determine if addressOrName is an address or name
	queryReq := &scriptv1.WebRequest{
		Httprequest: rawRequest,
	}

	// First, try to get script address/name from TXT records
	txtRecords, err := getTXTRecords(req.Host)
	if err == nil {
		// Prefer script address if available, otherwise use script name
		if txtRecords.ScriptAddress != "" {
			queryReq.ScriptAddress = txtRecords.ScriptAddress
			fmt.Printf("Found script address from TXT record: %s\n", queryReq.ScriptAddress)
		}
		if txtRecords.ScriptName != "" {
			queryReq.ScriptName = txtRecords.ScriptName
			fmt.Printf("Found script name from TXT record: %s\n", queryReq.ScriptName)
		}
	}

	// If no address or name found in TXT records, fall back to regex pattern with named captures
	if queryReq.ScriptAddress == "" && queryReq.ScriptName == "" {
		match := h.scriptAddressOrNameRe.FindStringSubmatch(req.Host)
		if len(match) == 0 {
			errorMsg := fmt.Sprintf("No match for host: `%s` using ScriptAddressOrNamePattern: `%s`", req.Host, h.scriptAddressOrNameRe.String())
			http.Error(w, errorMsg, http.StatusNotFound)
			return
		}
		fmt.Printf("Match for host: `%s` using ScriptAddressOrNamePattern: `%s`\n", req.Host, h.scriptAddressOrNameRe.String())

		names := h.scriptAddressOrNameRe.SubexpNames()
		for i := 1; i < len(match) && i < len(names); i++ {
			if match[i] == "" {
				continue
			}
			switch names[i] {
			case "address":
				queryReq.ScriptAddress = match[i]
				fmt.Printf("Found script address from regex: %s\n", queryReq.ScriptAddress)
			case "name":
				queryReq.ScriptName = match[i] + ".dys"
				fmt.Printf("Found script name from regex: %s\n", queryReq.ScriptName)
			}
		}

		if queryReq.ScriptAddress == "" && queryReq.ScriptName == "" {
			errorMsg := fmt.Sprintf("No named capture (address/name) extracted for host: `%s` using pattern: `%s`, raw match: %v", req.Host, h.scriptAddressOrNameRe.String(), match)
			http.Error(w, errorMsg, http.StatusNotFound)
			return
		}
	}

	// Create a response object
	resp := &scriptv1.WebResponse{}

	fmt.Printf("Querying script: %+v\n", queryReq)
	// Use clientCtx.Invoke instead of direct app.Query
	err = h.clientCtx.Invoke(req.Context(), "/dysonprotocol.script.v1.Query/Web", queryReq, resp)
	if err != nil {
		fmt.Println("[ERROR] DWApp Handler: Error querying app:", err)
		// If error is "failed to resolve script name: {name}", extract and handle special case for dys.dys
		errMsg := err.Error()
		re := regexp.MustCompile(`failed to resolve script name:\s*([^\s:]+)`)
		fmt.Printf("Error message: %s\n", errMsg)
		// If error is "script with address {addr} doesn't exist" return a friendly text hint
		addrRe := regexp.MustCompile(`script with address\s*([a-z0-9]+)\s*doesn't exist`)
		if m := addrRe.FindStringSubmatch(strings.ToLower(errMsg)); len(m) == 2 {
			addr := m[1]
			w.Header().Set("Content-Type", "text/plain; charset=utf-8")
			w.WriteHeader(http.StatusNotFound)
			fmt.Fprintf(w, "\"%s\" has not set up a Dys Dwapp yet.\n\n", addr)
			fmt.Fprint(w, "Minimal Hello World example (WSGI):\n\n")
			fmt.Fprint(w, "```python\n")
			fmt.Fprint(w, "# wsgi.py\n")
			fmt.Fprint(w, "def wsgi(environ, start_response):\n")
			fmt.Fprint(w, "    start_response('200 OK', [('Content-Type', 'text/plain')])\n")
			fmt.Fprint(w, "    return [b'Hello, world!']\n")
			fmt.Fprint(w, "```\n")
			return
		}
		if m := re.FindStringSubmatch(errMsg); len(m) == 2 {
			name := strings.TrimSpace(m[1])
			fmt.Printf("Failed to resolve script name: %s\n", name)

			// Redirect to dys registry for other names
			publicHost := strings.ReplaceAll(h.publicHostTemplate, "{address_or_name}", "dys")
			// relative protocol to all https or http
			target := "//" + publicHost + "/names/" + url.PathEscape(name)
			http.Redirect(w, req, target, http.StatusFound)
			return
		}
		http.Error(w, fmt.Sprintf("Error querying: %v", err), http.StatusInternalServerError)
		return
	}

	// get the last line
	lines := strings.Split(resp.Httpresponse, "\n")
	lastLine := lines[len(lines)-1]

	decoded, err := base64.StdEncoding.DecodeString(lastLine)
	if err != nil {
		fmt.Println("[ERROR] DWApp Handler: Error decoding response:", err)
		http.Error(w, "Error decoding", http.StatusInternalServerError)
		return
	}

	// write the response directly to the writer
	err = WriteRawResponse(decoded, w)

	if err != nil {
		fmt.Println("[ERROR] DWApp Handler: Error writing response:", err)
		http.Error(w, fmt.Sprintf("Error writing response: %v", err), http.StatusInternalServerError)
		return
	}
}

func WriteRawResponse(rawResponse []byte, w http.ResponseWriter) error {
	// Convert bytes to a buffered reader for easier line-by-line reading
	reader := bufio.NewReader(bytes.NewReader(rawResponse))

	// Read the status line
	statusLine, err := reader.ReadString('\n')
	if err != nil {
		return fmt.Errorf("failed to read status line: %v, %s", err, rawResponse)
	}
	statusLine = strings.TrimSpace(statusLine) // Remove any trailing whitespace

	// Parse the status line
	parts := strings.SplitN(statusLine, " ", 3)
	if len(parts) < 2 {
		return fmt.Errorf("malformed status line: '%s'", statusLine)
	}
	statusCode, err := strconv.Atoi(parts[1])
	if err != nil {
		return fmt.Errorf("invalid status code: %v", err)
	}

	// Read and set headers
	for {
		line, err := reader.ReadString('\n')
		if err != nil {
			return fmt.Errorf("failed to read header line: %v", err)
		}
		line = strings.TrimSpace(line)
		if line == "" {
			break // Headers section has ended
		}

		parts := strings.SplitN(line, ": ", 2)
		if len(parts) != 2 {
			return fmt.Errorf("malformed header: '%s'", line)
		}
		w.Header().Add(parts[0], parts[1])
	}

	// Set the status code
	w.WriteHeader(statusCode)

	// Write the body
	for {
		buffer := make([]byte, 1024)
		n, err := reader.Read(buffer)
		if err != nil && err.Error() != "EOF" {
			return fmt.Errorf("failed to read body: %v", err)
		}
		if n == 0 {
			break
		}
		_, err = w.Write(buffer[:n])
		if err != nil {
			return fmt.Errorf("failed to write body: %v", err)
		}
	}

	return nil
}

func getRawRequest(r *http.Request) (string, error) {
	var buf bytes.Buffer

	// Write the request method, URL, and protocol
	if _, err := fmt.Fprintf(&buf, "%s %s %s\r\n", r.Method, r.URL.RequestURI(), r.Proto); err != nil {
		return "", err
	}

	// Explicitly write Host header (not included in r.Header by default)
	if _, err := fmt.Fprintf(&buf, "Host: %s\r\n", r.Host); err != nil {
		return "", err
	}

	// Write the headers
	for k, vs := range r.Header {
		for _, v := range vs {
			if _, err := fmt.Fprintf(&buf, "%s: %s\r\n", k, v); err != nil {
				return "", err
			}
		}
	}

	// Write an extra CRLF to indicate the end of headers
	if _, err := fmt.Fprint(&buf, "\r\n"); err != nil {
		return "", err
	}

	// If there's a body, write it to the buffer
	if r.Body != nil {
		bodyBytes := new(bytes.Buffer)
		if _, err := bodyBytes.ReadFrom(r.Body); err != nil {
			return "", err
		}
		if _, err := buf.Write(bodyBytes.Bytes()); err != nil {
			return "", err
		}
		// IMPORTANT: Restore the body to the request object
		r.Body = io.NopCloser(bytes.NewBuffer(bodyBytes.Bytes()))
	}

	return buf.String(), nil
}

// getTXTRecords queries DNS TXT records for a domain and looks for DYSON_SCRIPT_NAME and DYSON_SCRIPT_ADDRESS entries
func getTXTRecords(host string) (DysonTxtRecords, error) {
	// Remove port if present
	domain, _, err := net.SplitHostPort(host)
	if err != nil {
		// If error, assume no port was present
		domain = host
	}

	// Query TXT records
	txtRecords, err := net.LookupTXT(domain)
	if err != nil {
		return DysonTxtRecords{}, err
	}

	result := DysonTxtRecords{}

	// Look for DYSON_SCRIPT_NAME or DYSON_SCRIPT_ADDRESS in TXT records
	for _, txt := range txtRecords {
		// Check if this TXT record contains either of our keys
		if strings.Contains(txt, txtScriptNameRecordKey+"=") || strings.Contains(txt, txtScriptAddressRecordKey+"=") {
			// Parse the TXT record as URL query parameters
			values, err := url.ParseQuery(txt)
			if err != nil {
				continue
			}

			// Extract script name if present
			if scriptNames := values[txtScriptNameRecordKey]; len(scriptNames) == 1 {
				result.ScriptName = strings.ToLower(strings.TrimSpace(scriptNames[0]))
			}

			// Extract script address if present
			if scriptAddresses := values[txtScriptAddressRecordKey]; len(scriptAddresses) == 1 {
				result.ScriptAddress = strings.ToLower(strings.TrimSpace(scriptAddresses[0]))
			}
		}
	}

	return result, nil
}

// isBrowserDialable checks if a multiaddr is dialable from a browser
func isBrowserDialable(addr string) bool {
	return strings.Contains(addr, "/ws") ||
		strings.Contains(addr, "/wss") ||
		strings.Contains(addr, "/webtransport")
}
