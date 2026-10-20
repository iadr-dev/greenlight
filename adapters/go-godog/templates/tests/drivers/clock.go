package drivers

import (
	"strings"
	"time"
)

// Clock is the injected clock. Application code reads world.Clock.Now (give it a clock seam); nothing freezes the
// process clock, because Go has no safe way to do that. Note the seam in system.md.
type Clock struct {
	now *time.Time
}

var layouts = []string{time.RFC3339, "2006-01-02T15:04:05", "2006-01-02 15:04:05", "2006-01-02 15:04", "2006-01-02"}

// Set freezes the clock at the given moment (UTC when no zone is given).
func (c *Clock) Set(text string) error {
	text = strings.TrimSpace(text)
	for _, layout := range layouts {
		if moment, err := time.ParseInLocation(layout, text, time.UTC); err == nil {
			c.now = &moment
			return nil
		}
	}
	return Assertf("cannot read the time %q (use 2026-03-01T09:00:00Z or 2026-03-01)", text)
}

// Advance moves the frozen clock on.
func (c *Clock) Advance(text string) error {
	if c.now == nil {
		return Assertf("set the current time first (Given the current time is ...)")
	}
	seconds, err := DurationSeconds(text)
	if err != nil {
		return err
	}
	moved := c.now.Add(time.Duration(seconds * float64(time.Second)))
	c.now = &moved
	return nil
}

// Now is the frozen moment, or the real time when none was set.
func (c *Clock) Now() time.Time {
	if c.now != nil {
		return *c.now
	}
	return time.Now().UTC()
}

// Stop releases the clock after the scenario.
func (c *Clock) Stop() { c.now = nil }
