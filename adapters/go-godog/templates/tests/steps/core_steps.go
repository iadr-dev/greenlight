// Package steps binds the core instructions of greenlight's step vocabulary to the drivers.
//
// Each step carries the id of the instruction it implements in a `// C.…` comment; the adapter's contract test checks
// that every instruction of the declared profiles is present. Steps only call drivers: no paths, no selectors, no SQL
// here. Project-specific steps that compose these live in their own file. The data table or doc string of a step is
// read with drivers.Payload(ctx), drivers.Table(ctx) or drivers.Text(ctx). More specific expressions come first:
// the first expression that matches a step wins.
package steps

import (
	"context"
	"strconv"

	"github.com/cucumber/godog"

	"greenlight.example/tests/drivers"
)

// Register binds every core instruction for one scenario.
func Register(sc *godog.ScenarioContext) {
	// -- Given ------------------------------------------------------------------------------------
	sc.Given(`^the following (.+) exist:$`, func(ctx context.Context, entity string) error { // C.ENTITY.SEED
		world := drivers.Of(ctx)
		world.Track(entity)
		return world.System.Seed(entity, drivers.Rows(drivers.Table(ctx)))
	})
	sc.Given(`^(.+) is signed in as (.+)$`, func(ctx context.Context, actor, role string) error { // C.ACTOR.AUTH
		world := drivers.Of(ctx)
		headers, err := world.System.Authenticate(actor, role)
		world.Headers[actor] = headers
		return err
	})
	sc.Given(`^the current time is (.+)$`, func(ctx context.Context, moment string) error { // C.CLOCK.SET
		return drivers.Of(ctx).Clock.Set(moment)
	})
	sc.Given(`^(.+) responds to (.+) with:$`, func(ctx context.Context, dependency, operation string) error { // C.STUB.RESPOND
		drivers.Of(ctx).Stubs.Respond(dependency, operation, drivers.Payload(ctx))
		return nil
	})
	sc.Given(`^the (.+) feature flag is (on|off)$`, func(ctx context.Context, flag, state string) error { // C.FLAG.SET
		return drivers.Of(ctx).System.SetFlag(flag, state == "on")
	})
	sc.Given(`^the input file (.+) contains:$`, func(ctx context.Context, file string) error { // C.FILE.GIVEN
		return drivers.Of(ctx).Workspace.Write(file, drivers.Text(ctx))
	})

	// -- When -------------------------------------------------------------------------------------
	sc.When(`^the (.+) event is received with:$`, func(ctx context.Context, event string) error { // C.EVENT.RECEIVE
		world := drivers.Of(ctx)
		if err := world.Act(); err != nil {
			return err
		}
		return world.System.DeliverEvent(event, drivers.Payload(ctx))
	})
	sc.When(`^the (.+) job runs$`, func(ctx context.Context, job string) error { // C.JOB.RUN
		world := drivers.Of(ctx)
		if err := world.Act(); err != nil {
			return err
		}
		return world.System.RunJob(job)
	})
	sc.When(`^(.+) is called with:$`, func(ctx context.Context, operation string) error { // C.LIB.CALL
		world := drivers.Of(ctx)
		if err := world.Act(); err != nil {
			return err
		}
		return drivers.CallLib(world, operation, drivers.Payload(ctx))
	})
	sc.When(`^(.+) calls (.+?)(?: with:)?$`, func(ctx context.Context, actor, operation string) error { // C.API.CALL
		world := drivers.Of(ctx)
		if err := world.Act(); err != nil {
			return err
		}
		return drivers.Call(world, actor, operation, drivers.Payload(ctx))
	})
	sc.When(`^(.+) runs (.+?)(?: with:)?$`, func(ctx context.Context, actor, command string) error { // C.CLI.RUN
		world := drivers.Of(ctx)
		if err := world.Act(); err != nil {
			return err
		}
		return drivers.Run(world, command, drivers.Table(ctx))
	})
	sc.When(`^(.+) passes$`, func(ctx context.Context, duration string) error { // C.CLOCK.ADVANCE
		return drivers.Of(ctx).Clock.Advance(duration)
	})

	// -- Then -------------------------------------------------------------------------------------
	sc.Then(`^the request succeeds$`, func(ctx context.Context) error { // C.API.STATUS
		return drivers.AssertSucceeds(drivers.Of(ctx))
	})
	sc.Then(`^the request is rejected with (.+)$`, func(ctx context.Context, name string) error { // C.API.STATUS
		return drivers.AssertRejected(drivers.Of(ctx), name)
	})
	sc.Then(`^the response contains:$`, func(ctx context.Context) error { // C.API.BODY
		outcome, err := drivers.Of(ctx).Last("api")
		if err != nil {
			return err
		}
		return drivers.AssertSubset(outcome.Body, drivers.Payload(ctx), "the response")
	})
	sc.Then(`^the (.+) records (are|include):$`, func(ctx context.Context, entity, mode string) error { // C.ENTITY.VERIFY
		actual, err := drivers.Of(ctx).System.Records(entity)
		if err != nil {
			return err
		}
		expected := drivers.Rows(drivers.Table(ctx))
		if mode == "include" {
			return drivers.AssertSubset(actual, expected, "the "+entity+" records")
		}
		return drivers.AssertSameRecords(actual, expected, "the "+entity+" records")
	})
	sc.Then(`^no (.+) records changed$`, func(ctx context.Context, entity string) error { // C.ENTITY.UNCHANGED
		return drivers.AssertUnchanged(drivers.Of(ctx), entity)
	})
	sc.Then(`^(.+) ran at most (\d+) queries$`, func(ctx context.Context, operation, count string) error { // C.QUERY.COUNT
		limit, err := strconv.Atoi(count)
		if err != nil {
			return err
		}
		return drivers.Of(ctx).AssertQueriesAtMost(operation, limit)
	})
	sc.Then(`^the (.+) event is published with:$`, func(ctx context.Context, event string) error { // C.EVENT.PUBLISHED
		published, err := drivers.Of(ctx).System.Published(event)
		if err != nil {
			return err
		}
		return drivers.AssertSubset(published, []any{drivers.Payload(ctx)}, "the "+event+" events")
	})
	sc.Then(`^(.+) received (.+) with:$`, func(ctx context.Context, dependency, operation string) error { // C.STUB.CALLED
		return drivers.Of(ctx).Stubs.AssertReceived(dependency, operation, drivers.Payload(ctx))
	})
	sc.Then(`^the command succeeds$`, func(ctx context.Context) error { // C.CLI.RESULT
		return drivers.AssertCommandSucceeds(drivers.Of(ctx))
	})
	sc.Then(`^the command fails with (.+)$`, func(ctx context.Context, name string) error { // C.CLI.RESULT
		return drivers.AssertCommandFails(drivers.Of(ctx), name)
	})
	sc.Then(`^the (stdout|stderr) output contains:$`, func(ctx context.Context, stream string) error { // C.OUTPUT.CONTAINS
		outcome, err := drivers.Of(ctx).Last("cli")
		if err != nil {
			return err
		}
		text := outcome.Stdout
		if stream == "stderr" {
			text = outcome.Stderr
		}
		return drivers.AssertTextContains(text, drivers.Text(ctx), "the "+stream+" output")
	})
	sc.Then(`^the output file (.+) contains:$`, func(ctx context.Context, file string) error { // C.FILE.VERIFY
		return drivers.Of(ctx).Workspace.AssertContains(file, drivers.Text(ctx))
	})
	sc.Then(`^the result is:$`, func(ctx context.Context) error { // C.LIB.RESULT
		return drivers.AssertResult(drivers.Of(ctx), drivers.Payload(ctx), true)
	})
	sc.Then(`^the result includes:$`, func(ctx context.Context) error { // C.LIB.RESULT
		return drivers.AssertResult(drivers.Of(ctx), drivers.Payload(ctx), false)
	})
	sc.Then(`^the call fails with (.+)$`, func(ctx context.Context, name string) error { // C.LIB.RESULT
		return drivers.AssertCallFails(drivers.Of(ctx), name)
	})
}
