package dysvm

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"regexp"
	"sync"
	"time"

	"dysonprotocol.com/dysvm/internal/data"
	"github.com/kluctl/go-embed-python/embed_util"
	"github.com/kluctl/go-embed-python/python"

	errorsmod "cosmossdk.io/errors"
)

type pyResponse struct {
	Ok     bool            `json:"ok"`
	Result json.RawMessage `json:"result"`
	Error  any             `json:"error"`
}

type PythonServer struct {
	mu      sync.Mutex
	cmd     *python.EmbeddedPython
	child   *exec.Cmd
	baseURL string
	client  *http.Client
}

var (
	serverOnce sync.Once
	serverInst *PythonServer
)

const defaultDeadline = 15 * time.Second

func getServer(ctx context.Context) *PythonServer {
	serverOnce.Do(func() {
		serverInst = &PythonServer{
			client: &http.Client{Timeout: 10 * time.Second},
		}
		err := serverInst.ensureStarted(ctx)
		if err != nil {
			fmt.Printf("failed to ensure dyslang server is started: %s\n", err)
		}
	})
	return serverInst
}

func (s *PythonServer) ensureStarted(ctx context.Context) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	fmt.Println("ensuring dyslang server is started")
	if s.baseURL != "" {
		// Health check
		req, err := http.NewRequestWithContext(ctx, http.MethodGet, s.baseURL+"/health", nil)
		if err != nil {
			return errorsmod.Wrapf(err, "failed to create health check request")
		}
		resp, err := s.client.Do(req)
		if err == nil && resp != nil && resp.StatusCode == 200 {
			_ = resp.Body.Close()
			fmt.Printf("existing server healthy\n")
			return nil
		}
		if resp != nil {
			_ = resp.Body.Close()
		}
		// Existing server unhealthy; reset and start a new one below
		s.baseURL = ""
		fmt.Printf("existing server unhealthy; resetting and starting a new one\n")

	}

	// Start embedded python with dyslang serve
	var lib *embed_util.EmbeddedFiles
	ep, err := python.NewEmbeddedPython("dyslang")
	if err != nil {
		return errorsmod.Wrapf(err, "failed to create embedded python")
	}

	lib, err = embed_util.NewEmbeddedFiles(data.Data, "dyslang-libs")

	if err != nil {
		return errorsmod.Wrapf(err, "failed to create embedded files")
	}
	// Add local package path and embedded libs
	ep.AddPythonPath("./dysvm/internal/py-dyslang")
	ep.AddPythonPath(lib.GetExtractedPath())

	// Always bind localhost and request ephemeral port 0; parse actual port from uvicorn output
	host := "127.0.0.1"
	cmd, err := ep.PythonCmd("-u", "-m", "dyslang", "serve", host, "0")
	if err != nil {
		return errorsmod.Wrapf(err, "failed to start dyslang server")
	}
	// Pipe server logs and discover the bound port from uvicorn output
	portCh := make(chan string, 1)
	if out, perr := cmd.StdoutPipe(); perr == nil {
		go streamLogsAndDiscover("stdout", out, portCh)
	}
	if er, perr := cmd.StderrPipe(); perr == nil {
		go streamLogsAndDiscover("stderr", er, portCh)
	}

	if err := cmd.Start(); err != nil {
		return errorsmod.Wrapf(err, "failed to start dyslang server")
	}
	s.cmd = ep
	s.child = cmd

	// Wait for uvicorn to report the listening port
	var discoveredPort string
	deadline := time.Now().Add(defaultDeadline)
	for time.Now().Before(deadline) {
		select {
		case p := <-portCh:
			if p != "" {
				discoveredPort = p
				goto GOT_PORT
			}
		case <-time.After(50 * time.Millisecond):
		}
	}
	return fmt.Errorf("dyslang server failed to report listening port")

GOT_PORT:
	s.baseURL = fmt.Sprintf("http://%s:%s", host, discoveredPort)
	fmt.Printf("dyslang server started on %s\n", s.baseURL)
	// Wait for health
	deadline = time.Now().Add(defaultDeadline)
	for time.Now().Before(deadline) {
		req, err := http.NewRequestWithContext(ctx, http.MethodGet, s.baseURL+"/health", nil)
		if err != nil {
			return errorsmod.Wrapf(err, "failed to create health check request")
		}
		resp, err := s.client.Do(req)
		if err == nil && resp != nil && resp.StatusCode == 200 {
			_ = resp.Body.Close()
			return nil
		}
		if resp != nil {
			_ = resp.Body.Close()
		}
		time.Sleep(100 * time.Millisecond)
	}
	return fmt.Errorf("dyslang server failed healthcheck")
}

func (s *PythonServer) request(ctx context.Context, path string, payload any) (json.RawMessage, error) {
	fmt.Println("requesting dyslang server")

	if err := s.ensureStarted(ctx); err != nil {
		return nil, errorsmod.Wrapf(err, "failed to ensure dyslang server is started")
	}
	body, err := json.Marshal(payload)
	if err != nil {
		return nil, errorsmod.Wrapf(err, "failed to marshal payload")
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, s.baseURL+path, bytes.NewReader(body))
	if err != nil {
		return nil, errorsmod.Wrapf(err, "failed to create request")
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := s.client.Do(req)
	if err != nil {
		fmt.Printf("failed to do request: %s\n", err)
		return nil, fmt.Errorf("failed to do request")
	}
	defer resp.Body.Close()
	var pr pyResponse
	dec := json.NewDecoder(resp.Body)
	if err := dec.Decode(&pr); err != nil {
		return nil, errorsmod.Wrapf(err, "failed to decode response")
	}
	if !pr.Ok {
		// If error is the wrapped eval response, normalize to {"exception": {...}} string
		if m, ok := pr.Error.(map[string]any); ok {
			var exc any
			if resp, ok2 := m["exception"]; ok2 {
				exc = resp
			} else {
				exc = m
			}
			wrapper, _ := json.Marshal(map[string]any{"exception": exc})
			return nil, fmt.Errorf("%s", string(wrapper))
		}
		b, _ := json.Marshal(map[string]any{"exception": pr.Error})
		return nil, fmt.Errorf("%s", string(b))
	}
	return pr.Result, nil
}

// Exec via server
func (s *PythonServer) Exec(ctx context.Context, msgJSON, scriptJSON, attachedMsgResultsJSON, headerInfoJSON, port string) (string, error) {
	ctx, cancel := context.WithTimeout(ctx, defaultDeadline)
	defer cancel()
	res, err := s.request(ctx, "/exec_script", map[string]any{
		"msg_json":                  msgJSON,
		"script_json":               scriptJSON,
		"attached_msg_results_json": attachedMsgResultsJSON,
		"header_info_json":          headerInfoJSON,
		"rpc_port":                  mustAtoi(port),
	})
	if err != nil {
		return "", errorsmod.Wrapf(err, "failed to exec script")
	}
	var out string
	if err := json.Unmarshal(res, &out); err != nil {
		// Result may already be a JSON string; return raw
		return string(res), nil
	}
	return out, nil
}

func (s *PythonServer) Wsgi(ctx context.Context, port, scriptName, scriptJSON, blockInfoJSON, httpreq string) (string, error) {
	ctx, cancel := context.WithTimeout(ctx, defaultDeadline)
	defer cancel()
	res, err := s.request(ctx, "/run_wsgi", map[string]any{
		"rpc_port":        mustAtoi(port),
		"script_name":     scriptName,
		"script_json":     scriptJSON,
		"block_info_json": blockInfoJSON,
		"http_request":    httpreq,
	})
	if err != nil {
		return "", errorsmod.Wrapf(err, "failed to run wsgi")
	}
	var out string
	if err := json.Unmarshal(res, &out); err != nil {
		return string(res), nil
	}
	return out, nil
}

func (s *PythonServer) Benchmark(ctx context.Context, iterations int, details bool) (string, error) {
	ctx, cancel := context.WithTimeout(ctx, defaultDeadline)
	defer cancel()
	res, err := s.request(ctx, "/run_benchmark", map[string]any{
		"iterations": iterations,
		"details":    details,
	})
	if err != nil {
		return "", errorsmod.Wrapf(err, "failed to run benchmark")
	}
	var out string
	if err := json.Unmarshal(res, &out); err != nil {
		return string(res), err
	}
	return out, nil
}

func (s *PythonServer) DysFormat(ctx context.Context, code string) (string, error) {
	ctx, cancel := context.WithTimeout(ctx, defaultDeadline)
	defer cancel()
	res, err := s.request(ctx, "/dys_format", map[string]any{
		"code": code,
	})
	// original code
	//fmt.Printf("dys format original code: %s\n", code)
	//fmt.Printf("dys format response: %s\n", string(res))
	if err != nil {
		fmt.Printf("dys format error: %s\n", err)
		return "", errorsmod.Wrapf(err, "failed to dys format")
	}
	var out string
	if err := json.Unmarshal(res, &out); err != nil {
		return string(res), err
	}
	return out, nil
}

func (s *PythonServer) ExtractFunctionSchema(ctx context.Context, scriptJSON, blockInfoJSON, port, executorAddress, scriptName string) (string, error) {
	ctx, cancel := context.WithTimeout(ctx, defaultDeadline)
	defer cancel()
	res, err := s.request(ctx, "/extract_function_schema", map[string]any{
		"script_json":      scriptJSON,
		"block_info_json":  blockInfoJSON,
		"rpc_port":         mustAtoi(port),
		"executor_address": executorAddress,
		"script_name":      scriptName,
	})
	if err != nil {
		return "", errorsmod.Wrapf(err, "failed to extract function schema")
	}
	var out string
	if err := json.Unmarshal(res, &out); err != nil {
		return string(res), nil
	}
	return out, nil
}

func mustAtoi(s string) int {
	var v int
	_, _ = fmt.Sscan(s, &v)
	return v
}

func streamLogs(tag string, r io.Reader) {
	br := bufio.NewScanner(r)
	for br.Scan() {
		fmt.Fprintf(os.Stderr, "[dyslang %s] %s\n", tag, br.Text())
	}
}

var uvicornURLRe = regexp.MustCompile(`Uvicorn running on http://127\.0\.0\.1:(\d+)`)

func streamLogsAndDiscover(tag string, r io.Reader, portCh chan<- string) {
	br := bufio.NewScanner(r)
	sent := false
	for br.Scan() {
		line := br.Text()
		if !sent {
			if m := uvicornURLRe.FindStringSubmatch(line); len(m) == 2 {
				portCh <- m[1]
				sent = true
			}
		}
		fmt.Fprintf(os.Stderr, "[dyslang %s] %s\n", tag, line)
	}
}
