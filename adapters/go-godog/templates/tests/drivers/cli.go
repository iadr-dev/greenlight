package drivers

import (
	"bytes"
	"context"
	"errors"
	"os"
	"os/exec"
	"strings"
	"time"
)

const commandTimeout = 60 * time.Second

// Run runs a command by its logical name in the scenario workspace.
//
// The table of a runs step has two columns, key and value. Keys: arg (repeat for several arguments), stdin, and
// env.NAME.
func Run(w *World, command string, table [][]string) error {
	words, ok := Commands[command]
	if !ok {
		return NotMapped{Kind: "command", Name: command, Known: keys(Commands)}
	}
	words = append([]string(nil), words...)
	stdin, env := "", os.Environ()
	for _, row := range skipHeader(table) {
		if len(row) < 2 {
			return Assertf("each row of the command table needs a key and a value")
		}
		switch key, value := row[0], row[1]; {
		case key == "arg":
			words = append(words, value)
		case key == "stdin":
			stdin = value
		case strings.HasPrefix(key, "env."):
			env = append(env, key[4:]+"="+value)
		default:
			return Assertf("unknown key %q in the command table (use arg, stdin or env.NAME)", key)
		}
	}
	limit, cancel := context.WithTimeout(context.Background(), commandTimeout)
	defer cancel()
	process := exec.CommandContext(limit, words[0], words[1:]...) // #nosec G204 -- the program comes from the Commands map, not from a scenario
	process.Dir, process.Env = w.Workspace.Root, env
	var out, errOut bytes.Buffer
	process.Stdin, process.Stdout, process.Stderr = strings.NewReader(stdin), &out, &errOut
	code := 0
	if err := process.Run(); err != nil {
		var exit *exec.ExitError
		if !errors.As(err, &exit) {
			return Assertf("the command %q could not run: %v", command, err)
		}
		code = exit.ExitCode()
	}
	w.Outcome = &Outcome{Kind: "cli", ExitCode: code, Stdout: out.String(), Stderr: errOut.String()}
	return nil
}

func skipHeader(table [][]string) [][]string {
	if len(table) == 0 {
		return nil
	}
	return table[1:]
}

// AssertCommandSucceeds fails unless the last command exited with 0.
func AssertCommandSucceeds(w *World) error {
	outcome, err := w.Last("cli")
	if err != nil {
		return err
	}
	if outcome.ExitCode != 0 {
		return Assertf("the command should succeed but exited %d: %q", outcome.ExitCode, strings.TrimSpace(outcome.Stderr))
	}
	return nil
}

// AssertCommandFails fails unless the last command failed in the way the logical error says.
func AssertCommandFails(w *World, name string) error {
	outcome, err := w.Last("cli")
	if err != nil {
		return err
	}
	if outcome.ExitCode == 0 {
		return Assertf("the command should fail but it succeeded")
	}
	matched, err := outcome.MatchesError(name)
	if err != nil {
		return err
	}
	if !matched {
		return Assertf("the command failed, but not with %q: exit %d, %q", name, outcome.ExitCode, strings.TrimSpace(outcome.Stderr))
	}
	return nil
}
