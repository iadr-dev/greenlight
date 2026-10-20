package drivers

import "net/http"

// System holds the seams into the system under test. This is the one file of drivers that is specific to the project.
//
// Every method says what it does and returns ExpectedMissing until the project implements the seam: during the red
// phase that is the right failure. Use the most realistic seam available: the HTTP handler first, then a domain
// service, then a repository, then the raw database. Add the fields you need (a handler, a database, a counter).
type System struct {
	Clock *Clock // the scenario's clock: give the application a clock seam that reads it
	Stubs *Stubs // the scenario's stubbed dependencies: route the application's outbound calls through them
}

// -- Given ----------------------------------------------------------------------------------------

// Seed creates rows of an entity. An unknown column is an error.
func (s *System) Seed(entity string, rows []map[string]any) error {
	return ExpectedMissing("a way to create " + entity + " records")
}

// Authenticate signs the actor in with the role and returns the HTTP headers that prove it.
func (s *System) Authenticate(actor, role string) (http.Header, error) {
	return nil, ExpectedMissing("a way to sign in as " + role)
}

// SetFlag configures a feature flag or setting.
func (s *System) SetFlag(flag string, enabled bool) error {
	return ExpectedMissing("the " + flag + " feature flag")
}

// -- When -----------------------------------------------------------------------------------------

// Handler is the application's HTTP handler. Requests are served in memory (net/http/httptest), so no port is opened.
func (s *System) Handler() (http.Handler, error) {
	return nil, ExpectedMissing("an HTTP handler for the application")
}

// DeliverEvent hands an event to the application.
func (s *System) DeliverEvent(event string, payload any) error {
	return ExpectedMissing("a way to deliver the " + event + " event")
}

// RunJob runs a scheduled job once.
func (s *System) RunJob(job string) error {
	return ExpectedMissing("the " + job + " job")
}

// Complete fills in request fields the scenario did not give, for example the id of the order created earlier, so a
// step like `alice calls look up order` needs no id. The default adds nothing.
func (s *System) Complete(operation string, fields map[string]any) map[string]any {
	return fields
}

// -- Then -----------------------------------------------------------------------------------------

// Records returns every stored record of an entity, read through a seam that does not change anything.
func (s *System) Records(entity string) ([]map[string]any, error) {
	return nil, ExpectedMissing("a way to read " + entity + " records")
}

// QueriesExecuted is how many database statements have run since the scenario began. Install a QueryCounter (see
// queries.go) on the application's data access when the system is built and return its Count. Only scenarios that check
// a query count need this seam.
func (s *System) QueriesExecuted() (int, error) {
	return 0, ExpectedMissing("a counter of the application's database statements")
}

// Published returns the payloads of an event that the application published (a test double of the broker).
func (s *System) Published(event string) ([]any, error) {
	return nil, ExpectedMissing("a captured " + event + " event")
}

// Reset is called after every scenario: drop data, close clients.
func (s *System) Reset() {}
