package drivers

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"strings"
)

// Outcome is what the last action did: an API response, a command, or a library call.
type Outcome struct {
	Kind      string // api | cli | lib
	Status    int    // api
	Body      any    // api: parsed body; lib: the returned value
	ExitCode  int    // cli
	Stdout    string // cli
	Stderr    string // cli
	Err       error  // lib: the error the call returned
	Operation string // api, lib: the logical name that was called
}

// MatchesError says whether the outcome is the logical error “name“ (see ERRORS in operations.go).
func (o *Outcome) MatchesError(name string) (bool, error) {
	rule, ok := Errors[name]
	if !ok {
		return false, NotMapped{Kind: "error", Name: name, Known: keys(Errors)}
	}
	text := strings.ToLower(strings.Join([]string{fmt.Sprint(o.Body), o.Stderr, o.Stdout, errorText(o.Err)}, " "))
	checks := []bool{
		len(rule.Statuses) == 0 || contains(rule.Statuses, o.Status),
		rule.ErrorType == "" || fmt.Sprintf("%T", o.Err) == rule.ErrorType,
		rule.ExitCode == nil || *rule.ExitCode == o.ExitCode,
		rule.Text == "" || strings.Contains(text, strings.ToLower(rule.Text)),
	}
	for _, check := range checks {
		if !check {
			return false, nil
		}
	}
	return len(rule.Statuses) > 0 || rule.ErrorType != "" || rule.ExitCode != nil || rule.Text != "", nil
}

func errorText(err error) string {
	if err == nil {
		return ""
	}
	return err.Error()
}

func contains(list []int, value int) bool {
	for _, item := range list {
		if item == value {
			return true
		}
	}
	return false
}

func keys[V any](m map[string]V) []string {
	out := make([]string, 0, len(m))
	for key := range m {
		out = append(out, key)
	}
	return out
}

// World is everything one scenario knows. A fresh World is made for every scenario, so nothing leaks between them.
type World struct {
	System    *System
	Clock     *Clock
	Stubs     *Stubs
	Workspace *Workspace
	Headers   map[string]http.Header // actor -> auth headers
	Outcome   *Outcome
	tracked   map[string]bool
	before    map[string][]map[string]any
	queries   *int // statements run before the last action
}

type worldKey struct{}

// NewWorld makes the world of one scenario and puts it in the context.
func NewWorld(ctx context.Context) (context.Context, error) {
	dir, err := os.MkdirTemp("", "greenlight-scenario-")
	if err != nil {
		return ctx, err
	}
	clock, stubs := &Clock{}, &Stubs{}
	world := &World{System: &System{Clock: clock, Stubs: stubs}, Clock: clock, Stubs: stubs, Workspace: &Workspace{Root: dir},
		Headers: map[string]http.Header{}, tracked: map[string]bool{}}
	return context.WithValue(ctx, worldKey{}, world), nil
}

// Of is the world of the scenario that is running.
func Of(ctx context.Context) *World {
	world, ok := ctx.Value(worldKey{}).(*World)
	if !ok {
		panic("no world: the scenario's before hook did not run (see tests/bdd_test.go)")
	}
	return world
}

// Close drops what the scenario made: the system's data and the workspace.
func (w *World) Close() {
	w.System.Reset()
	w.Clock.Stop()
	_ = os.RemoveAll(w.Workspace.Root)
}

// Track remembers an entity the scenario seeded or verified.
func (w *World) Track(entity string) { w.tracked[entity] = true }

// Act is called before every action: it remembers what every tracked entity looked like before the first one, and how
// many database statements had run before this one.
func (w *World) Act() error {
	if w.before == nil {
		w.before = map[string][]map[string]any{}
		for entity := range w.tracked {
			records, err := w.System.Records(entity)
			if err != nil {
				return err
			}
			w.before[entity] = copyRecords(records)
		}
	}
	w.queries = nil
	if count, err := w.System.QueriesExecuted(); err == nil {
		w.queries = &count // only a scenario that counts needs the seam
	}
	return nil
}

func copyRecords(records []map[string]any) []map[string]any {
	encoded, _ := json.Marshal(records)
	var copied []map[string]any
	_ = json.Unmarshal(encoded, &copied)
	return copied
}

// AssertQueriesAtMost fails when the last action ran more than “limit“ statements (an N+1 problem shows as a count
// that grows with the rows).
func (w *World) AssertQueriesAtMost(operation string, limit int) error {
	if w.Outcome != nil && w.Outcome.Operation != "" && w.Outcome.Operation != operation {
		return Assertf("the last action was %q, not %q", w.Outcome.Operation, operation)
	}
	total, err := w.System.QueriesExecuted() // ExpectedMissing without a counter
	if err != nil {
		return err
	}
	if w.queries == nil {
		return Assertf("no action ran before this check: a When step has to run first")
	}
	if ran := total - *w.queries; ran > limit {
		return Assertf("%s ran %d queries, more than the %d allowed (a count that grows with the number of records is an N+1 problem)",
			operation, ran, limit)
	}
	return nil
}

// Last is the outcome of the last action, which must be of the given kind.
func (w *World) Last(kind string) (*Outcome, error) {
	if w.Outcome == nil {
		return nil, Assertf("there is no result yet: a When step (%s) has to run first", kind)
	}
	if w.Outcome.Kind != kind {
		return nil, Assertf("the last action was %s, not %s", w.Outcome.Kind, kind)
	}
	return w.Outcome, nil
}

// AssertUnchanged fails unless the entity's records are what they were before the first action.
func AssertUnchanged(w *World, entity string) error {
	before, tracked := w.Before(entity)
	if !tracked {
		return Assertf("%s records were not tracked: seed them in a Given step (the following %s exist:) so that their state can be compared",
			entity, entity)
	}
	actual, err := w.System.Records(entity)
	if err != nil {
		return err
	}
	return AssertSameRecords(actual, before, "the "+entity+" records")
}

// Before is what an entity looked like before the first action.
func (w *World) Before(entity string) ([]map[string]any, bool) {
	records, ok := w.before[entity]
	return records, ok && w.before != nil
}
