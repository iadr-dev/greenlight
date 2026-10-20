package drivers

import "fmt"

// Stubs are the stubbed external dependencies. Route the application's outbound calls through
// world.Stubs.Call(dependency, operation, request) (a gateway interface) or an http.RoundTripper built on it. A call the
// scenario did not stub fails the scenario.
type Stubs struct {
	responses map[[2]string]any
	calls     []stubCall
}

type stubCall struct {
	dependency, operation string
	request               any
}

// Respond says what a dependency answers to an operation.
func (s *Stubs) Respond(dependency, operation string, response any) {
	if s.responses == nil {
		s.responses = map[[2]string]any{}
	}
	s.responses[[2]string{dependency, operation}] = response
}

// Call is what the application's gateway calls instead of the real dependency.
func (s *Stubs) Call(dependency, operation string, request any) (any, error) {
	s.calls = append(s.calls, stubCall{dependency, operation, request})
	response, ok := s.responses[[2]string{dependency, operation}]
	if !ok {
		return nil, UnstubbedCall{Dependency: dependency, Operation: operation}
	}
	return response, nil
}

// AssertReceived fails unless the dependency received the operation (with at least the expected fields, when given).
func (s *Stubs) AssertReceived(dependency, operation string, expected any) error {
	var requests []any
	var seen []string
	for _, call := range s.calls {
		seen = append(seen, call.dependency+"/"+call.operation)
		if call.dependency == dependency && call.operation == operation {
			requests = append(requests, call.request)
		}
	}
	if len(requests) == 0 {
		return Assertf("%s never received %s; it received %v", dependency, operation, seen)
	}
	if expected == nil {
		return nil
	}
	problems := ""
	for _, request := range requests {
		err := AssertSubset(request, expected, fmt.Sprintf("%s %s", dependency, operation))
		if err == nil {
			return nil
		}
		problems += err.Error() + "; "
	}
	return Assertf("%s", problems)
}
