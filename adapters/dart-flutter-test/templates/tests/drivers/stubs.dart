// Stubbed external dependencies.
//
// Route the application's outbound calls through `world.stubs.call(dependency, operation, request)` (a repository or
// gateway interface that the test implements). A call the scenario did not stub fails the scenario.
import 'package:flutter_test/flutter_test.dart';

import 'compare.dart';
import 'errors.dart';

class Stubs {
  final _responses = <String, Object?>{};
  final calls = <({String dependency, String operation, Object? request})>[];

  void respond(String dependency, String operation, Object? response) => _responses['$dependency.$operation'] = response;

  Object? call(String dependency, String operation, [Object? request]) {
    calls.add((dependency: dependency, operation: operation, request: request));
    final key = '$dependency.$operation';
    if (!_responses.containsKey(key)) {
      throw UnstubbedCall('$dependency was asked to $operation but the scenario did not stub it');
    }
    return _responses[key];
  }

  void assertReceived(String dependency, String operation, Object? expected) {
    final requests = [
      for (final call in calls)
        if (call.dependency == dependency && call.operation == operation) call.request,
    ];
    expect(requests, isNotEmpty,
        reason: '$dependency never received $operation; it received ${calls.map((c) => '${c.dependency}.${c.operation}').toList()}');
    final nothingExpected = expected == null || (expected is Iterable && expected.isEmpty) || (expected is Map && expected.isEmpty);
    if (!nothingExpected) {
      assertSubset(requests, [expected], 'the $operation requests received by $dependency');
    }
  }
}
