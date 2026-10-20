"""The core instructions of greenlight's step vocabulary, bound to the drivers.

Each step carries the id of the instruction it implements in a `# C.…` comment; the adapter's contract test
checks that every instruction of the declared profiles is present. Steps only call drivers: no paths, no
selectors, no SQL here. Project-specific steps that compose these live in their own module.
"""
from __future__ import annotations

from pytest_bdd import given, parsers, then, when

from tests.drivers import api, cli, compare, lib
from tests.drivers.world import World


# -- Given ---------------------------------------------------------------------------------------
@given(parsers.parse("the following {entity} exist:"))                       # C.ENTITY.SEED
def entities_exist(world: World, entity, datatable):
    world.track(entity)
    world.system.seed(entity, compare.rows(datatable))


@given(parsers.parse("{actor} is signed in as {role}"))                      # C.ACTOR.AUTH
def actor_signed_in(world: World, actor, role):
    world.headers[actor] = world.system.authenticate(actor, role)


@given(parsers.parse("the current time is {datetime}"))                      # C.CLOCK.SET
def time_is(world: World, datetime):
    world.clock.set(datetime)


@given(parsers.parse("{dependency} responds to {operation} with:"))          # C.STUB.RESPOND
def dependency_responds(world: World, dependency, operation, docstring=None, datatable=None):
    world.stubs.respond(dependency, operation, compare.payload(datatable, docstring))


@given(parsers.re(r"the (?P<flag>.+) feature flag is (?P<state>on|off)"))   # C.FLAG.SET
def flag_is(world: World, flag, state):
    world.system.set_flag(flag, state == "on")


@given(parsers.parse("the input file {file} contains:"))                     # C.FILE.GIVEN
def input_file(world: World, file, docstring=None, datatable=None):
    text = docstring if docstring is not None else "\n".join(",".join(row) for row in datatable or [])
    world.workspace.write(file, text)


# -- When ----------------------------------------------------------------------------------------
@when(parsers.re(r"(?P<actor>.+?) calls (?P<operation>.+?)(?: with:)?"))     # C.API.CALL
def api_call(world: World, actor, operation, docstring=None, datatable=None):
    world.act()
    api.call(world, actor, operation, compare.payload(datatable, docstring))


@when(parsers.re(r"(?P<actor>.+?) runs (?P<command>.+?)(?: with:)?"))       # C.CLI.RUN
def cli_run(world: World, actor, command, datatable=None):
    world.act()
    cli.run(world, command, datatable)


@when(parsers.parse("{operation} is called with:"))                          # C.LIB.CALL
def lib_call(world: World, operation, docstring=None, datatable=None):
    world.act()
    lib.call(world, operation, compare.payload(datatable, docstring))


@when(parsers.parse("the {event} event is received with:"))                  # C.EVENT.RECEIVE
def event_received(world: World, event, docstring=None, datatable=None):
    world.act()
    world.system.deliver_event(event, compare.payload(datatable, docstring))


@when(parsers.parse("the {job} job runs"))                                   # C.JOB.RUN
def job_runs(world: World, job):
    world.act()
    world.system.run_job(job)


@when(parsers.parse("{duration} passes"))                                    # C.CLOCK.ADVANCE
def time_passes(world: World, duration):
    world.clock.advance(duration)


# -- Then ----------------------------------------------------------------------------------------
@then("the request succeeds")                                                # C.API.STATUS
def request_succeeds(world: World):
    api.assert_succeeds(world)


@then(parsers.parse("the request is rejected with {error}"))                 # C.API.STATUS
def request_rejected(world: World, error):
    api.assert_rejected(world, error)


@then("the response contains:")                                              # C.API.BODY
def response_contains(world: World, docstring=None, datatable=None):
    compare.assert_subset(world.last("api").body, compare.payload(datatable, docstring), "the response")


@then(parsers.re(r"the (?P<entity>.+) records (?P<mode>are|include):"))      # C.ENTITY.VERIFY
def records_verified(world: World, entity, mode, datatable):
    actual, expected = world.system.records(entity), compare.rows(datatable)
    if mode == "include":
        compare.assert_subset(actual, expected, f"the {entity} records")
    else:
        key = compare.sort_key
        compare.assert_equal(sorted(actual, key=key), sorted(expected, key=key), f"the {entity} records")


@then(parsers.parse("no {entity} records changed"))                          # C.ENTITY.UNCHANGED
def records_unchanged(world: World, entity):
    assert world.before is not None and entity in world.before, (
        f"{entity} records were not tracked: seed them in a Given step (the following {entity} exist:) so that "
        "their state can be compared")
    compare.assert_equal(world.system.records(entity), world.before[entity], f"the {entity} records")


@then(parsers.parse("the {event} event is published with:"))                 # C.EVENT.PUBLISHED
def event_published(world: World, event, docstring=None, datatable=None):
    compare.assert_subset(world.system.published(event), [compare.payload(datatable, docstring)], f"the {event} events")


@then(parsers.parse("{dependency} received {operation} with:"))             # C.STUB.CALLED
def dependency_received(world: World, dependency, operation, docstring=None, datatable=None):
    world.stubs.assert_received(dependency, operation, compare.payload(datatable, docstring))


@then("the command succeeds")                                                # C.CLI.RESULT
def command_succeeds(world: World):
    cli.assert_succeeds(world)


@then(parsers.parse("the command fails with {error}"))                       # C.CLI.RESULT
def command_fails(world: World, error):
    cli.assert_fails(world, error)


@then(parsers.re(r"the (?P<stream>stdout|stderr) output contains:"))         # C.OUTPUT.CONTAINS
def output_contains(world: World, stream, docstring=None, datatable=None):
    text = docstring if docstring is not None else "\n".join(",".join(row) for row in datatable or [])
    compare.assert_text_contains(getattr(world.last("cli"), stream), text, f"the {stream} output")


@then(parsers.parse("the output file {file} contains:"))                     # C.FILE.VERIFY
def output_file_contains(world: World, file, docstring=None, datatable=None):
    text = docstring if docstring is not None else "\n".join(",".join(row) for row in datatable or [])
    world.workspace.assert_contains(file, text)


@then("the result is:")                                                      # C.LIB.RESULT
def result_is(world: World, docstring=None, datatable=None):
    lib.assert_result(world, compare.payload(datatable, docstring), exact=True)


@then("the result includes:")                                                # C.LIB.RESULT
def result_includes(world: World, docstring=None, datatable=None):
    lib.assert_result(world, compare.payload(datatable, docstring), exact=False)


@then(parsers.parse("the call fails with {error}"))                          # C.LIB.RESULT
def call_fails(world: World, error):
    lib.assert_fails(world, error)
