// Package drivers holds everything the steps call: the world of one scenario, the seams into the system under test,
// and the helpers that turn Gherkin tables into data and compare data. Steps never contain paths, binaries or
// selectors; the logical names are mapped in operations.go.
package drivers

import (
	"fmt"
	"sort"
)

// Marker is what the red gate classifies on: a failure that contains it is an expected failure.
const Marker = "BDD_EXPECTED_MISSING"

// ExpectedMissing says that the system under test does not have this yet. During the red phase that is the right failure.
func ExpectedMissing(what string) error {
	return fmt.Errorf("%s: %s does not exist yet", Marker, what)
}

// UnstubbedCall is the failure when the system called an external dependency that the scenario did not stub.
type UnstubbedCall struct{ Dependency, Operation string }

func (e UnstubbedCall) Error() string {
	return fmt.Sprintf("UnstubbedCall: %s was asked to %s but the scenario did not stub it", e.Dependency, e.Operation)
}

// OutboundNetworkBlocked is the failure when a real network connection was attempted. Stub the dependency instead.
type OutboundNetworkBlocked struct{ Address string }

func (e OutboundNetworkBlocked) Error() string {
	return fmt.Sprintf("OutboundNetworkBlocked: a real connection to %s was attempted; stub the dependency instead", e.Address)
}

// NotMapped is a defect of the test, not a missing feature: a logical name in a feature has no entry in operations.go.
type NotMapped struct {
	Kind, Name string
	Known      []string
}

func (e NotMapped) Error() string {
	known := append([]string(nil), e.Known...)
	sort.Strings(known)
	return fmt.Sprintf("NotMapped: no %s named %q in tests/drivers/operations.go (known: %v)", e.Kind, e.Name, known)
}

// Failure is an assertion that did not hold.
type Failure struct{ Message string }

func (e Failure) Error() string { return "AssertionError: " + e.Message }

// Assertf builds a Failure; steps return it as their error.
func Assertf(format string, args ...any) error {
	return Failure{Message: fmt.Sprintf(format, args...)}
}
