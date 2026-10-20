// Command csvtool reads CSV files. Today it only counts rows; reports are the feature to be built.
package main

import (
	"encoding/csv"
	"fmt"
	"io"
	"os"
)

const (
	exitOK      = 0
	exitInvalid = 1
	exitUsage   = 2
)

func main() {
	os.Exit(run(os.Args[1:], os.Stdout, os.Stderr))
}

// run executes one command line and returns the exit status.
func run(args []string, stdout, stderr io.Writer) int {
	if len(args) == 0 {
		fmt.Fprintln(stderr, "usage: csvtool count FILE")
		return exitUsage
	}
	switch args[0] {
	case "count":
		return count(args[1:], stdout, stderr)
	default:
		fmt.Fprintf(stderr, "unknown command %q\n", args[0])
		return exitUsage
	}
}

// count prints the number of data rows (the header is not counted).
func count(args []string, stdout, stderr io.Writer) int {
	if len(args) != 1 {
		fmt.Fprintln(stderr, "usage: csvtool count FILE")
		return exitUsage
	}
	file, err := os.Open(args[0])
	if err != nil {
		fmt.Fprintf(stderr, "cannot open %s: %v\n", args[0], err)
		return exitInvalid
	}
	defer file.Close()
	rows, err := csv.NewReader(file).ReadAll()
	if err != nil {
		fmt.Fprintf(stderr, "invalid CSV: %v\n", err)
		return exitInvalid
	}
	if len(rows) == 0 {
		fmt.Fprintln(stderr, "empty file: there is no header row")
		return exitInvalid
	}
	fmt.Fprintf(stdout, "%d rows\n", len(rows)-1)
	return exitOK
}
