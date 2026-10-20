package drivers

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
)

// Call calls an API operation by its logical name and keeps what came back.
func Call(w *World, actor, operation string, data any) error {
	route, ok := API[operation]
	if !ok {
		return NotMapped{Kind: "API operation", Name: operation, Known: keys(API)}
	}
	handler, err := w.System.Handler()
	if err != nil {
		return err
	}
	given, _ := data.(map[string]any)
	fields := w.System.Complete(operation, given) // the project may add what the scenario left out
	path, sent := route.Path, map[string]any{}
	for name, value := range fields {
		if placeholder := "{" + name + "}"; strings.Contains(path, placeholder) {
			path = strings.ReplaceAll(path, placeholder, url.PathEscape(textOf(value)))
		} else {
			sent[name] = value
		}
	}
	method := strings.ToUpper(route.Method)
	var body *bytes.Reader
	switch {
	case method == http.MethodGet && len(sent) > 0:
		query := url.Values{}
		for name, value := range sent {
			query.Set(name, textOf(value))
		}
		path += "?" + query.Encode()
		body = bytes.NewReader(nil)
	case given == nil && data != nil: // a list or a plain value is sent as it is
		encoded, _ := json.Marshal(data)
		body = bytes.NewReader(encoded)
	case len(sent) > 0:
		encoded, _ := json.Marshal(sent)
		body = bytes.NewReader(encoded)
	default:
		body = bytes.NewReader(nil)
	}
	request := httptest.NewRequest(method, path, body)
	request.Header.Set("Content-Type", "application/json")
	for name, values := range w.Headers[actor] {
		for _, value := range values {
			request.Header.Add(name, value)
		}
	}
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	var parsed any
	if json.Unmarshal(recorder.Body.Bytes(), &parsed) != nil {
		parsed = recorder.Body.String()
	}
	w.Outcome = &Outcome{Kind: "api", Status: recorder.Code, Body: parsed, Operation: operation}
	return nil
}

func textOf(value any) string {
	if text, ok := value.(string); ok {
		return text
	}
	encoded, _ := json.Marshal(value)
	return string(encoded)
}

// AssertSucceeds fails unless the last response was a success (2xx).
func AssertSucceeds(w *World) error {
	outcome, err := w.Last("api")
	if err != nil {
		return err
	}
	if outcome.Status < 200 || outcome.Status >= 300 {
		return Assertf("the request should succeed but got status %d: %v", outcome.Status, outcome.Body)
	}
	return nil
}

// AssertRejected fails unless the last response was an error that matches the logical error.
func AssertRejected(w *World, name string) error {
	outcome, err := w.Last("api")
	if err != nil {
		return err
	}
	if outcome.Status < 400 {
		return Assertf("the request should be rejected but got status %d", outcome.Status)
	}
	matched, err := outcome.MatchesError(name)
	if err != nil {
		return err
	}
	if !matched {
		return Assertf("the request was rejected, but not with %q: status %d, %v", name, outcome.Status, outcome.Body)
	}
	return nil
}
