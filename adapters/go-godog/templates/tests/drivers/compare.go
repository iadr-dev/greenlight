package drivers

import (
	"context"
	"encoding/json"
	"fmt"
	"reflect"
	"regexp"
	"sort"
	"strconv"
	"strings"

	"github.com/cucumber/godog"
)

type argumentKey struct{}

// WithStep keeps the step that is about to run, so a step function needs only the words it matched and reads the data
// table or doc string here. tests/bdd_test.go installs it as a before-step hook.
func WithStep(ctx context.Context, step *godog.Step) context.Context {
	return context.WithValue(ctx, argumentKey{}, step)
}

func argument(ctx context.Context) *godog.Step {
	found, _ := ctx.Value(argumentKey{}).(*godog.Step)
	return found
}

// Table is the data table of the current step, as rows of cells, or nil.
func Table(ctx context.Context) [][]string {
	step := argument(ctx)
	if step == nil || step.Argument == nil || step.Argument.DataTable == nil {
		return nil
	}
	rows := make([][]string, 0, len(step.Argument.DataTable.Rows))
	for _, row := range step.Argument.DataTable.Rows {
		cells := make([]string, 0, len(row.Cells))
		for _, cell := range row.Cells {
			cells = append(cells, cell.Value)
		}
		rows = append(rows, cells)
	}
	return rows
}

// DocString is the doc string of the current step.
func DocString(ctx context.Context) (string, bool) {
	step := argument(ctx)
	if step == nil || step.Argument == nil || step.Argument.DocString == nil {
		return "", false
	}
	return step.Argument.DocString.Content, true
}

// ParseValue reads a cell or doc string as data: JSON when it parses (numbers, true, null, lists, objects), else the text.
func ParseValue(text string) any {
	text = strings.TrimSpace(text)
	var value any
	if err := json.Unmarshal([]byte(text), &value); err != nil {
		return text
	}
	return value
}

// Rows turns a table with a header row into a list of records.
func Rows(table [][]string) []map[string]any {
	if len(table) == 0 {
		return nil
	}
	rows := make([]map[string]any, 0, len(table)-1)
	for _, line := range table[1:] {
		row := map[string]any{}
		for i, name := range table[0] {
			if i < len(line) {
				row[name] = ParseValue(line[i])
			}
		}
		rows = append(rows, row)
	}
	return rows
}

// Payload is the data a step carries: a doc string as JSON or text, or a table (one row becomes an object).
func Payload(ctx context.Context) any {
	if text, ok := DocString(ctx); ok {
		return ParseValue(text)
	}
	rows := Rows(Table(ctx))
	if len(rows) == 1 {
		return rows[0]
	}
	if rows == nil {
		return nil
	}
	items := make([]any, len(rows))
	for i, row := range rows {
		items[i] = row
	}
	return items
}

// Text is the step's doc string, or its table with comma-separated rows.
func Text(ctx context.Context) string {
	if text, ok := DocString(ctx); ok {
		return text
	}
	lines := []string{}
	for _, row := range Table(ctx) {
		lines = append(lines, strings.Join(row, ","))
	}
	return strings.Join(lines, "\n")
}

// SortKey is a stable order for comparing record sets whose order does not matter.
func SortKey(row any) string {
	encoded, _ := json.Marshal(row) // map keys are sorted by encoding/json
	return string(encoded)
}

// NormaliseText ignores line endings, trailing blanks and blank lines.
func NormaliseText(text string) string {
	lines := []string{}
	for _, line := range strings.Split(strings.ReplaceAll(strings.TrimSpace(text), "\r\n", "\n"), "\n") {
		if strings.TrimSpace(line) != "" {
			lines = append(lines, strings.TrimRight(line, " \t"))
		}
	}
	return strings.Join(lines, "\n")
}

// normal makes data comparable: whatever the project's code returned is passed through JSON, so structs, ints and
// maps compare the same way as what a scenario wrote.
func normal(value any) any {
	encoded, err := json.Marshal(value)
	if err != nil {
		return value
	}
	var out any
	if json.Unmarshal(encoded, &out) != nil {
		return value
	}
	return out
}

// AssertEqual fails unless the data is equal.
func AssertEqual(actual, expected any, what string) error {
	if reflect.DeepEqual(normal(actual), normal(expected)) {
		return nil
	}
	return Assertf("%s: expected %s but got %s", what, SortKey(expected), SortKey(actual))
}

// AssertSameRecords fails unless both record sets hold the same records, in any order.
func AssertSameRecords(actual, expected []map[string]any, what string) error {
	return AssertEqual(sortedByKey(actual), sortedByKey(expected), what)
}

func sortedByKey(rows []map[string]any) []any {
	items := make([]any, len(rows))
	for i, row := range rows {
		items[i] = normal(row)
	}
	sort.Slice(items, func(i, j int) bool { return SortKey(items[i]) < SortKey(items[j]) })
	return items
}

// AssertSubset fails unless every field of expected is in actual (recursively); lists must contain each expected item.
func AssertSubset(actual, expected any, what string) error {
	if problem := subsetProblem(normal(actual), normal(expected), ""); problem != "" {
		return Assertf("%s: %s (actual: %s)", what, problem, SortKey(actual))
	}
	return nil
}

func joinPath(path, key string) string {
	if path == "" {
		return key
	}
	return path + "." + key
}

func orValue(path string) string {
	if path == "" {
		return "value"
	}
	return path
}

func subsetProblem(actual, expected any, path string) string {
	switch want := expected.(type) {
	case map[string]any:
		return objectProblem(actual, want, path)
	case []any:
		return listProblem(actual, want, path)
	}
	if reflect.DeepEqual(actual, expected) {
		return ""
	}
	return fmt.Sprintf("%s is %s, expected %s", orValue(path), SortKey(actual), SortKey(expected))
}

// objectProblem says why actual does not hold every field of want, or "" when it does.
func objectProblem(actual any, want map[string]any, path string) string {
	have, ok := actual.(map[string]any)
	if !ok {
		return orValue(path) + " should be an object"
	}
	keys := make([]string, 0, len(want))
	for key := range want {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	for _, key := range keys {
		value, present := have[key]
		if !present {
			return joinPath(path, key) + " is missing"
		}
		if problem := subsetProblem(value, want[key], joinPath(path, key)); problem != "" {
			return problem
		}
	}
	return ""
}

// listProblem says why actual lacks an item matching one of want, or "" when it has them all.
func listProblem(actual any, want []any, path string) string {
	have, ok := actual.([]any)
	if !ok {
		return orValue(path) + " should be a list"
	}
	for _, item := range want {
		if !containsMatch(have, item, path) {
			return fmt.Sprintf("%s has no item matching %s", orValue(path), SortKey(item))
		}
	}
	return ""
}

func containsMatch(candidates []any, item any, path string) bool {
	for _, candidate := range candidates {
		if subsetProblem(candidate, item, path) == "" {
			return true
		}
	}
	return false
}

// AssertTextContains fails unless the text contains the expected text, ignoring line endings and blank lines.
func AssertTextContains(actual, expected, what string) error {
	wanted, got := NormaliseText(expected), NormaliseText(actual)
	if strings.Contains(got, wanted) {
		return nil
	}
	return Assertf("%s does not contain %q; it is %q", what, wanted, got)
}

var durationPattern = regexp.MustCompile(`(?i)(\d+(?:\.\d+)?)\s*(seconds?|secs?|s|minutes?|mins?|m|hours?|hrs?|h|days?|d|weeks?|w)\b`)

var unitSeconds = map[byte]float64{'s': 1, 'm': 60, 'h': 3600, 'd': 86400, 'w': 604800}

// DurationSeconds reads '2 days', '30 minutes' or '1h 30m' as seconds.
func DurationSeconds(text string) (float64, error) {
	found := durationPattern.FindAllStringSubmatch(text, -1)
	rest := strings.Trim(durationPattern.ReplaceAllString(text, ""), " ,and")
	if len(found) == 0 || rest != "" {
		return 0, Assertf("cannot read the duration %q", text)
	}
	total := 0.0
	for _, match := range found {
		number, _ := strconv.ParseFloat(match[1], 64)
		total += number * unitSeconds[strings.ToLower(match[2])[0]]
	}
	return total, nil
}
