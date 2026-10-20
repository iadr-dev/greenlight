package drivers

import "fmt"

// CallLib calls a public function by its logical name; the returned value or the returned error is kept.
func CallLib(w *World, operation string, data any) error {
	function, ok := Lib[operation]
	if !ok {
		return NotMapped{Kind: "library operation", Name: operation, Known: keys(Lib)} // an unmapped function is a failure, not a result
	}
	value, err := function(data)
	w.Outcome = &Outcome{Kind: "lib", Body: value, Err: err, Operation: operation}
	return nil
}

// AssertResult fails unless the last call returned the expected value (exactly, or as a subset).
func AssertResult(w *World, expected any, exact bool) error {
	outcome, err := w.Last("lib")
	if err != nil {
		return err
	}
	if outcome.Err != nil {
		return Assertf("the call returned the error %T: %v", outcome.Err, outcome.Err)
	}
	if exact {
		return AssertEqual(outcome.Body, expected, "the result")
	}
	return AssertSubset(outcome.Body, expected, "the result")
}

// AssertCallFails fails unless the last call returned an error that matches the logical error.
func AssertCallFails(w *World, name string) error {
	outcome, err := w.Last("lib")
	if err != nil {
		return err
	}
	if outcome.Err == nil {
		return Assertf("the call should fail but returned %v", outcome.Body)
	}
	matched, err := outcome.MatchesError(name)
	if err != nil {
		return err
	}
	if !matched {
		return Assertf("the call failed, but not with %q: %s", name, fmt.Sprintf("%T: %v", outcome.Err, outcome.Err))
	}
	return nil
}
