/// Calling a public function by its logical name; the return value or the error it throws is kept.
library;

import 'package:flutter_test/flutter_test.dart';

import 'compare.dart';
import 'errors.dart';
import 'operations.dart';
import 'world.dart';

String _describe(Object? error) => error is DriverError ? '$error' : '${error.runtimeType}: $error';

Future<void> call(World world, String operation, Object? data) async {
  final mapped = lib[operation];
  if (mapped == null) {
    throw NotMapped('library operation', operation, lib.keys); // a missing name is a failure, not a result
  }
  try {
    world.outcome = LibOutcome(operation, value: await mapped(data));
  } on ExpectedMissing {
    rethrow; // the code under test does not exist yet: that is the red phase, not a result to judge
  } on Object catch (error) {
    world.outcome = LibOutcome(operation, error: error); // the scenario decides whether this error was wanted
  }
}

void assertResult(World world, Object? expected, {required bool exact}) {
  final outcome = world.last();
  if (outcome.error != null) {
    throw TestFailure('the call threw ${_describe(outcome.error)}');
  }
  (exact ? assertEqual : assertSubset)(outcome.value, expected, 'the result');
}

void assertFails(World world, String name) {
  final outcome = world.last();
  if (outcome.error == null) {
    throw TestFailure('the call should fail but returned ${outcome.value}');
  }
  if (!world.matchesError(outcome, name)) {
    throw TestFailure("the call failed, but not with '$name': ${_describe(outcome.error)}");
  }
}
