/// The core instructions of greenlight's step vocabulary, bound to the drivers.
///
/// Each step carries the id of the instruction it implements in a `// C.…` comment; the adapter's contract test checks
/// that every instruction of the declared profiles is present. Steps only call drivers: no widget keys, no import paths,
/// no SQL here. Project-specific steps that compose these live in `project_steps.dart`.
library;

import '../drivers/compare.dart';
import '../drivers/lib.dart' as lib;
import '../drivers/ui.dart' as ui;
import 'definition.dart';

final coreSteps = <StepDefinition>[
  // -- Given ---------------------------------------------------------------------------------------------------------
  given(r'^the following (.+) exist:$', (world, words, argument) async { // C.ENTITY.SEED
    world.tracked.add(words[0]);
    await world.system.seed(words[0], rows(argument?.table));
  }),
  given(r'^(.+) is signed in as (.+)$', (world, words, argument) async { // C.ACTOR.AUTH
    world.logins[words[0]] = await world.system.authenticate(words[0], words[1]);
  }),
  given(r'^the current time is (.+)$', (world, words, argument) async { // C.CLOCK.SET
    await world.system.setTime(world.clock.set(words[0]));
  }),
  given(r'^(.+) responds to (.+) with:$', (world, words, argument) async { // C.STUB.RESPOND
    world.stubs.respond(words[0], words[1], payload(argument));
  }),
  given(r'^the (.+) feature flag is (on|off)$', (world, words, argument) async { // C.FLAG.SET
    await world.system.setFlag(words[0], enabled: words[1] == 'on');
  }),
  given(r'^the application state is:$', (world, words, argument) async { // C.STATE.GLOBAL
    ui.setState(world, argument);
  }),

  // -- When ----------------------------------------------------------------------------------------------------------
  when(r'^([\w.-]+) opens the (.+) page$', (world, words, argument) async { // C.UI.OPEN
    await world.act();
    await ui.open(world, words[1]);
  }),
  when(r'^([\w.-]+) (clicks|fills|selects|uploads|types|toggles) ([^:\n]+?)(?: with:)?$', (world, words, argument) async { // C.UI.ACT
    await world.act();
    await ui.act(world, ui.Action.values.byName(words[1]), words[2], argument);
  }),
  when(r'^the (.+) event is received with:$', (world, words, argument) async { // C.EVENT.RECEIVE
    await world.act();
    await world.system.deliverEvent(words[0], payload(argument));
  }),
  when(r'^the (.+) job runs$', (world, words, argument) async { // C.JOB.RUN
    await world.act();
    await world.system.runJob(words[0]);
  }),
  when(r'^(.+) passes$', (world, words, argument) async { // C.CLOCK.ADVANCE
    await world.system.setTime(world.clock.advance(words[0]));
  }),
  when(r'^(.+) is called with:$', (world, words, argument) async { // C.LIB.CALL
    await world.act();
    await lib.call(world, words[0], payload(argument));
  }),

  // -- Then ----------------------------------------------------------------------------------------------------------
  then(r'^([\w.-]+) sees ([^:\n]+) showing:$', (world, words, argument) async { // C.UI.SEE
    ui.assertShows(words[1], argument);
  }),
  then(r'^([\w.-]+) does not see (.+)$', (world, words, argument) async { // C.UI.NOT_SEE
    ui.assertHidden(words[1]);
  }),
  then(r'^the application state includes:$', (world, words, argument) async { // C.STATE.VERIFY
    await ui.assertState(world, argument);
  }),
  then(r'^the (.+) records (are|include):$', (world, words, argument) async { // C.ENTITY.VERIFY
    final actual = await world.system.records(words[0]);
    final expected = rows(argument?.table);
    if (words[1] == 'include') {
      assertSubset(actual, expected, 'the ${words[0]} records');
    } else {
      assertEqual(_sorted(actual), _sorted(expected), 'the ${words[0]} records');
    }
  }),
  then(r'^no (.+) records changed$', (world, words, argument) async { // C.ENTITY.UNCHANGED
    final before = world.before?[words[0]];
    if (before == null) {
      throw StateError('${words[0]} records were not tracked: seed them in a Given step (the following ${words[0]} exist:) '
          'so that their state can be compared');
    }
    assertEqual(await world.system.records(words[0]), before, 'the ${words[0]} records');
  }),
  then(r'^the (.+) event is published with:$', (world, words, argument) async { // C.EVENT.PUBLISHED
    assertSubset(await world.system.published(words[0]), [payload(argument)], 'the ${words[0]} events');
  }),
  then(r'^(.+) received (.+) with:$', (world, words, argument) async { // C.STUB.CALLED
    world.stubs.assertReceived(words[0], words[1], payload(argument));
  }),
  then(r'^the result is:$', (world, words, argument) async { // C.LIB.RESULT
    lib.assertResult(world, payload(argument), exact: true);
  }),
  then(r'^the result includes:$', (world, words, argument) async { // C.LIB.RESULT
    lib.assertResult(world, payload(argument), exact: false);
  }),
  then(r'^the call fails with (.+)$', (world, words, argument) async { // C.LIB.RESULT
    lib.assertFails(world, words[0]);
  }),
];

List<Object?> _sorted(List<Object?> records) => [...records]..sort((a, b) => sortKey(a).compareTo(sortKey(b)));
