package main

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func writeCSV(t *testing.T, text string) string {
	t.Helper()
	path := filepath.Join(t.TempDir(), "data.csv")
	if err := os.WriteFile(path, []byte(text), 0o600); err != nil {
		t.Fatal(err)
	}
	return path
}

func runCommand(args ...string) (int, string, string) {
	var out, errOut bytes.Buffer
	status := run(args, &out, &errOut)
	return status, out.String(), errOut.String()
}

func TestCountSkipsTheHeader(t *testing.T) {
	path := writeCSV(t, "region,amount\nnorth,10\nsouth,20\n")
	status, out, _ := runCommand("count", path)
	if status != exitOK || strings.TrimSpace(out) != "2 rows" {
		t.Fatalf("got status %d and output %q", status, out)
	}
}

func TestCountRefusesAMissingFile(t *testing.T) {
	status, _, errOut := runCommand("count", filepath.Join(t.TempDir(), "absent.csv"))
	if status != exitInvalid || !strings.Contains(errOut, "cannot open") {
		t.Fatalf("got status %d and error %q", status, errOut)
	}
}

func TestCountRefusesARaggedFileAndAnEmptyOne(t *testing.T) {
	status, _, errOut := runCommand("count", writeCSV(t, "a,b\n1\n"))
	if status != exitInvalid || !strings.Contains(errOut, "invalid CSV") {
		t.Fatalf("ragged: got status %d and error %q", status, errOut)
	}
	status, _, errOut = runCommand("count", writeCSV(t, ""))
	if status != exitInvalid || !strings.Contains(errOut, "empty file") {
		t.Fatalf("empty: got status %d and error %q", status, errOut)
	}
}

func TestUsageErrors(t *testing.T) {
	if status, _, _ := runCommand(); status != exitUsage {
		t.Fatalf("no arguments: got status %d", status)
	}
	if status, _, _ := runCommand("frobnicate"); status != exitUsage {
		t.Fatalf("unknown command: got status %d", status)
	}
	if status, _, _ := runCommand("count"); status != exitUsage {
		t.Fatalf("count without a file: got status %d", status)
	}
}
