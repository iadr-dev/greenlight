/// The seams into the system under test. This is the one file of drivers that is specific to the project.
///
/// Every method says what it does and fails with ExpectedMissing until the project implements the seam: during the red
/// phase that is the right failure. Use the most realistic seam available: a repository or use case first, then the
/// raw storage. Implement a seam as an `async` method (or return a Future); the steps wait for it.
library;

import 'clock.dart';
import 'compare.dart';
import 'errors.dart';
import 'stubs.dart';

export 'compare.dart' show Row;

/// A seam the project has not built yet: it fails the step as an expected failure.
Future<T> missing<T>(String what) => Future<T>.error(ExpectedMissing(what));

class System {
  /// [clock] is the scenario's time and [stubs] its stubbed dependencies: hand them to the application's seams.
  System(this.clock, this.stubs);

  final Clock clock;
  final Stubs stubs;

  /// Called once, before the first action of a scenario: start the application (a fake backend, a database).
  Future<void> start() async {}

  /// Called after every scenario: drop data, close clients.
  Future<void> reset() async {}

  /// The scenario's clock is set already (`world.clock`). Override this if the application needs the same time.
  Future<void> setTime(DateTime moment) async {}

  // -- Given: set the scene --------------------------------------------------------------------
  /// Create [rows] of [entity]. An unknown column is an error.
  Future<void> seed(String entity, List<Row> rows) => missing('a way to create $entity records');

  /// Sign [actor] in with [role]; what is returned is kept as `world.logins[actor]` for the application to use.
  Future<Object?> authenticate(String actor, String role) => missing('a way to sign in as $role');

  Future<void> setFlag(String flag, {required bool enabled}) => missing('the $flag feature flag');

  // -- When: act on the system -----------------------------------------------------------------
  Future<void> deliverEvent(String event, Object? payload) => missing('a way to deliver the $event event');

  Future<void> runJob(String job) => missing('the $job job');

  // -- Then: read the result -------------------------------------------------------------------
  /// Every stored [entity] record, read through a seam that does not change anything.
  Future<List<Row>> records(String entity) => missing('a way to read $entity records');

  /// The payloads of [event] that the application published (a test double of the broker).
  Future<List<Object?>> published(String event) => missing('a captured $event event');

  /// The client-side state of the application (preferences, a store), as a map.
  Future<Map<String, Object?>> applicationState() => missing('a way to read the application state');
}
