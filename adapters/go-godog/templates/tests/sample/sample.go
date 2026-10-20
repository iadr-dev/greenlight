// Package sample is the code the sample feature tests. Delete it with the sample.
package sample

// NegativeInput is returned when a number is below zero.
type NegativeInput struct{ Value int }

func (e NegativeInput) Error() string { return "negative input" }

// Add returns the sum of two non-negative numbers.
func Add(a, b int) (int, error) {
	if a < 0 {
		return 0, NegativeInput{Value: a}
	}
	if b < 0 {
		return 0, NegativeInput{Value: b}
	}
	return a + b, nil
}
