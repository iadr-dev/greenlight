// The one test that runs the feature files. `bdd run` starts it as
//
//	go -C tests test -mod=readonly -count=1 -run '^TestFeatures$' . -args -bdd.tag=FEAT-007 -bdd.out report.xml
//
// and reads the JUnit report. This file is bound: it is locked with the steps and drivers.
package tests

import (
	"context"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"testing"

	"github.com/cucumber/godog"

	"greenlight.example/tests/drivers"
	"greenlight.example/tests/steps"
)

var (
	tagFlag      = flag.String("bdd.tag", "", "run only the scenarios of this feature tag, for example FEAT-007")
	outFlag      = flag.String("bdd.out", "", "write the JUnit report to this file")
	seedFlag     = flag.Int64("bdd.seed", 0, "run the scenarios in a random order made repeatable by this seed (0 keeps the file order)")
	scenarioFlag = flag.String("bdd.scenario", "", "run only the scenario with this exact name")
)

const featuresDir = "features"

var scenarioLine = regexp.MustCompile(`^\s*Scenario(?: Outline| Template)?:\s*(.+?)\s*$`)

// scenarioPaths finds the file:line of the scenario with the given name, so that only that one runs.
func scenarioPaths(name string) ([]string, error) {
	var found []string
	err := filepath.Walk(featuresDir, func(path string, info os.FileInfo, err error) error {
		if err != nil || info.IsDir() || !strings.HasSuffix(path, ".feature") {
			return err
		}
		content, err := os.ReadFile(path) // #nosec G304 -- walking the features folder
		if err != nil {
			return err
		}
		for number, line := range strings.Split(string(content), "\n") {
			if match := scenarioLine.FindStringSubmatch(line); match != nil && match[1] == name {
				found = append(found, fmt.Sprintf("%s:%d", filepath.ToSlash(path), number+1))
			}
		}
		return nil
	})
	if err == nil && len(found) == 0 {
		err = fmt.Errorf("no scenario named %q in %s", name, featuresDir)
	}
	return found, err
}

func initializeScenario(sc *godog.ScenarioContext) {
	sc.Before(func(ctx context.Context, _ *godog.Scenario) (context.Context, error) {
		return drivers.NewWorld(ctx)
	})
	sc.After(func(ctx context.Context, _ *godog.Scenario, _ error) (context.Context, error) {
		drivers.Of(ctx).Close()
		return ctx, nil
	})
	sc.StepContext().Before(func(ctx context.Context, step *godog.Step) (context.Context, error) {
		return drivers.WithStep(ctx, step), nil // the data table or doc string of the step
	})
	steps.Register(sc)
}

func TestFeatures(t *testing.T) {
	drivers.BlockNetwork()
	options := godog.Options{Format: "junit", Paths: []string{featuresDir}, Strict: true, NoColors: true, Randomize: *seedFlag}
	if *tagFlag != "" {
		options.Tags = "@" + strings.TrimPrefix(*tagFlag, "@")
	}
	if *scenarioFlag != "" {
		paths, err := scenarioPaths(*scenarioFlag)
		if err != nil {
			t.Fatal(err)
		}
		options.Paths = paths
	}
	if *outFlag != "" {
		report, err := os.Create(*outFlag) // #nosec G304 -- the report path is given by bdd run
		if err != nil {
			t.Fatal(err)
		}
		defer report.Close()
		options.Output = report
	}
	suite := godog.TestSuite{Name: "greenlight", ScenarioInitializer: initializeScenario, Options: &options}
	if status := suite.Run(); status != 0 {
		t.Fatalf("godog finished with status %d", status)
	}
}
