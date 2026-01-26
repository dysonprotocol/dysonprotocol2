package dwapp

import (
	"encoding/json"
	"fmt"
	"html"
	"net/http"
	"strings"
)

// ErrorResponse represents the structured error data for 404 responses
type ErrorResponse struct {
	Error   string `json:"error"`
	Code    int    `json:"code"`
	Input   string `json:"input"`
	Message string `json:"message"`
	Hint    string `json:"hint"`
}

// ContentType represents supported response content types
type ContentType int

const (
	ContentTypePlain ContentType = iota
	ContentTypeJSON
	ContentTypeHTML
)

// negotiateContentType parses the Accept header and returns the best content type
func negotiateContentType(acceptHeader string) ContentType {
	if strings.TrimSpace(acceptHeader) == "" {
		return ContentTypePlain
	}

	for _, entry := range strings.Split(acceptHeader, ",") {
		mediaType := strings.TrimSpace(entry)
		if mediaType == "" {
			continue
		}
		if semi := strings.Index(mediaType, ";"); semi != -1 {
			mediaType = strings.TrimSpace(mediaType[:semi])
		}
		switch strings.ToLower(mediaType) {
		case "application/json":
			return ContentTypeJSON
		case "text/html":
			return ContentTypeHTML
		case "text/plain":
			return ContentTypePlain
		default:
			continue
		}
	}

	// Default to plain text
	return ContentTypePlain
}

// writeNotFoundResponse writes a 404 response with content negotiation
// publicHostTemplate is used to generate hints about where to register/deploy (e.g., "{address_or_name}.localhost:1317")
func writeNotFoundResponse(w http.ResponseWriter, req *http.Request, publicHostTemplate, input, message, hint string) {
	contentType := negotiateContentType(req.Header.Get("Accept"))

	switch contentType {
	case ContentTypeJSON:
		writeJSONNotFound(w, publicHostTemplate, input, message, hint)
	case ContentTypeHTML:
		writeHTMLNotFound(w, publicHostTemplate, input, message, hint)
	default:
		writePlainNotFound(w, publicHostTemplate, input, message, hint)
	}
}

// writeJSONNotFound writes a JSON-formatted 404 response
func writeJSONNotFound(w http.ResponseWriter, publicHostTemplate, input, message, hint string) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(http.StatusNotFound)

	// Generate example URL for hint
	exampleHost := exampleHostFromTemplate(publicHostTemplate)
	fullHint := fmt.Sprintf("%s Visit %s to deploy your dwapp.", hint, exampleHost)

	resp := ErrorResponse{
		Error:   "not_found",
		Code:    404,
		Input:   input,
		Message: message,
		Hint:    fullHint,
	}

	json.NewEncoder(w).Encode(resp)
}

// writeHTMLNotFound writes an HTML-formatted 404 response
func writeHTMLNotFound(w http.ResponseWriter, publicHostTemplate, input, message, hint string) {
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	w.WriteHeader(http.StatusNotFound)

	// Escape user input to prevent XSS
	escapedInput := html.EscapeString(input)
	escapedMessage := html.EscapeString(message)

	// Generate example URL from template
	exampleHost := exampleHostFromTemplate(publicHostTemplate)

	fmt.Fprintf(w, `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>404 Not Found - Dyson Protocol</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 800px; margin: 40px auto; padding: 0 20px; color: #333; }
        h1 { color: #e74c3c; }
        code { background: #f4f4f4; padding: 2px 6px; border-radius: 3px; font-family: 'SF Mono', Monaco, monospace; }
        pre { background: #2d2d2d; color: #f8f8f2; padding: 16px; border-radius: 6px; overflow-x: auto; }
        .hint { background: #e8f4fd; border-left: 4px solid #3498db; padding: 12px; margin: 20px 0; }
    </style>
</head>
<body>
    <h1>404 Not Found</h1>
    <p><strong>Input:</strong> <code>%s</code></p>
    <p><strong>Error:</strong> %s</p>
    <div class="hint">
        <h3>How to Fix</h3>
        <p>%s</p>
        <p>Once deployed, your dwapp will be available at: <code>%s</code></p>
    </div>
    <h3>Minimal Hello World Example (WSGI)</h3>
    <pre><code class="language-python"># wsgi.py
def wsgi(environ, start_response):
    start_response('200 OK', [('Content-Type', 'text/plain')])
    return [b'Hello, world!']</code></pre>
</body>
</html>`, escapedInput, escapedMessage, hint, exampleHost)
}

// writePlainNotFound writes a plain text 404 response
func writePlainNotFound(w http.ResponseWriter, publicHostTemplate, input, message, hint string) {
	w.Header().Set("Content-Type", "text/plain; charset=utf-8")
	w.WriteHeader(http.StatusNotFound)

	// Generate example URL from template
	exampleHost := exampleHostFromTemplate(publicHostTemplate)

	fmt.Fprintf(w, "%s\n\n", message)
	if hint != "" {
		fmt.Fprintf(w, "%s\n\n", hint)
	}
	fmt.Fprintf(w, "Once deployed, your dwapp will be available at: %s\n\n", exampleHost)
	fmt.Fprint(w, "Minimal Hello World example (WSGI, v2):\n\n")
	fmt.Fprint(w, "```python\n")
	fmt.Fprint(w, "# wsgi.py\n")
	fmt.Fprint(w, "def wsgi(environ, start_response):\n")
	fmt.Fprint(w, "    start_response('200 OK', [('Content-Type', 'text/plain')])\n")
	fmt.Fprint(w, "    return [b'Hello, world!']\n")
	fmt.Fprint(w, "```\n")
}

func exampleHostFromTemplate(publicHostTemplate string) string {
	template := strings.TrimSpace(publicHostTemplate)
	if template == "" || !strings.Contains(template, "{address_or_name}") {
		template = DefaultPublicHostTemplate
	}
	return strings.ReplaceAll(template, "{address_or_name}", "yourname")
}
