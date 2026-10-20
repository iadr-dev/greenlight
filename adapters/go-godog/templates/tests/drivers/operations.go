package drivers

import (
	"fmt"

	"greenlight.example/tests/sample"
)

// The map from the logical names used in features to this system. Features never contain paths, binaries or package
// names. The step-engineer fills this in from the system map (system.md); the sample entries belong to the sample
// feature and can be deleted with it.

// Route is an API operation: the method and the path, which may contain {field}, filled from the request data.
type Route struct{ Method, Path string }

// ErrorRule says what a logical error looks like. Any field that is set must match.
type ErrorRule struct {
	Statuses  []int  // HTTP status codes
	ErrorType string // the Go type of the returned error, as printed by %T
	ExitCode  *int   // process exit code
	Text      string // text in the response body, stderr or the error message
}

// API maps a logical name to a route.
var API = map[string]Route{
	// "place order": {"POST", "/orders"},
}

// Commands maps a logical name to a command line (program and arguments), started in the scenario workspace.
var Commands = map[string][]string{
	// "export report": {"go", "run", "./cmd/report"},
}

// Lib maps a logical name to a public function. The data of the step is passed as a map (a table row or a JSON
// object), a list or a plain value; the function returns the result or an error.
var Lib = map[string]func(input any) (any, error){
	"add": func(input any) (any, error) { // sample
		fields, _ := input.(map[string]any)
		a, aok := fields["a"].(float64)
		b, bok := fields["b"].(float64)
		if !aok || !bok {
			return nil, fmt.Errorf("add needs the numbers a and b")
		}
		return sample.Add(int(a), int(b))
	},
}

// Files maps a logical file name to a path relative to the scenario workspace.
var Files = map[string]string{
	// "report": "out/report.txt",
}

// Errors maps a logical error to what it looks like.
var Errors = map[string]ErrorRule{
	"negative input": {ErrorType: "sample.NegativeInput"}, // sample
	// "validation error": {Statuses: []int{400, 422}},
}
