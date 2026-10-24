/// Everything one scenario knows. A fresh World is made for every scenario, so nothing leaks between them.
library;

import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';

import 'clock.dart';
import 'errors.dart';
import 'operations.dart';
import 'stubs.dart';
import 'system.dart';

/// What the last library call did: the value it returned, or the error it threw.
class LibOutcome {
  const LibOutcome(this.operation, {this.value, this.error});

  final String operation;
  final Object? value;
  final Object? error;
}

class World {
  World(this.tester);

  final WidgetTester tester;
  final clock = Clock();
  final stubs = Stubs();
  late final system = System(clock, stubs);
  final logins = <String, Object?>{}; // actor -> what System.authenticate returned
  final appState = <String, Object?>{}; // the application state the scenario started from
  final tracked = <String>{}; // entities seeded or verified
  Map<String, List<Row>>? before;
  LibOutcome? outcome;
  var _started = false;

  /// Called before every action: start the system once, and remember what every tracked entity looked like before the
  /// first action.
  Future<void> act() async {
    if (!_started) {
      _started = true;
      await system.start();
    }
    if (before == null) {
      final snapshot = <String, List<Row>>{};
      for (final entity in tracked.toList()..sort()) {
        snapshot[entity] = (jsonDecode(jsonEncode(await system.records(entity))) as List).cast<Row>();
      }
      before = snapshot;
    }
  }

  LibOutcome last() {
    final found = outcome;
    if (found == null) {
      throw TestFailure('there is no result yet: a When step (a library call) has to run first');
    }
    return found;
  }

  /// Does the last outcome match the logical error [name]? An error name with no rule is a defect of the test.
  bool matchesError(LibOutcome found, String name) {
    final rule = errors[name];
    if (rule == null) {
      throw NotMapped('error', name, errors.keys);
    }
    final error = found.error;
    final message = error is DriverError ? error.message : '$error';
    final checks = [
      rule.exception == null || (error != null && error.runtimeType.toString() == rule.exception),
      rule.text == null || message.toLowerCase().contains(rule.text!.toLowerCase()),
    ];
    return (rule.exception != null || rule.text != null) && checks.every((ok) => ok);
  }

  Future<void> finish() => system.reset();
}
