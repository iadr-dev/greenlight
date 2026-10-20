package drivers

import (
	"os"
	"path/filepath"
	"strings"
)

// Workspace is an isolated directory per scenario, with files addressed by logical name.
type Workspace struct{ Root string }

func (w *Workspace) path(name string) (string, error) {
	relative, ok := Files[name]
	if !ok {
		return "", NotMapped{Kind: "file", Name: name, Known: keys(Files)}
	}
	target := filepath.Join(w.Root, filepath.FromSlash(relative))
	if inside, err := filepath.Rel(w.Root, target); err != nil || strings.HasPrefix(inside, "..") {
		return "", Assertf("%q maps outside the workspace", name)
	}
	return target, nil
}

// Write creates the file with the content.
func (w *Workspace) Write(name, content string) error {
	target, err := w.path(name)
	if err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(target), 0o750); err != nil {
		return err
	}
	return os.WriteFile(target, []byte(content), 0o600)
}

// Read returns the content of a file the scenario's action produced.
func (w *Workspace) Read(name string) (string, error) {
	target, err := w.path(name)
	if err != nil {
		return "", err
	}
	content, err := os.ReadFile(target) // #nosec G304 -- the path is a mapped name inside the scenario workspace
	if err != nil {
		return "", Assertf("the file %q (%s) was not produced", name, Files[name])
	}
	return string(content), nil
}

// AssertContains fails unless the file contains the expected text.
func (w *Workspace) AssertContains(name, expected string) error {
	got, err := w.Read(name)
	if err != nil {
		return err
	}
	wanted, normal := NormaliseText(expected), NormaliseText(got)
	if !strings.Contains(normal, wanted) {
		return Assertf("file %q does not contain %q; it is %q", name, wanted, normal)
	}
	return nil
}
