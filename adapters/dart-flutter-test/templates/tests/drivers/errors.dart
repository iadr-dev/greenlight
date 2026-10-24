// Errors the drivers throw. The marker in ExpectedMissing is what the red gate classifies on.
const marker = 'BDD_EXPECTED_MISSING';

/// An exception that prints as `ClassName: message`, so the test report shows what kind of failure it was.
class DriverError implements Exception {
  const DriverError(this.message);

  final String message;

  @override
  String toString() => '$runtimeType: $message';
}

/// The system under test does not have this yet. During the red phase this is the right failure.
class ExpectedMissing extends DriverError {
  ExpectedMissing(String what) : super('$marker: $what does not exist yet');
}

/// The system called an external dependency that the scenario did not stub.
class UnstubbedCall extends DriverError {
  const UnstubbedCall(super.message);
}

/// A real network connection was attempted. Stub the dependency instead.
class OutboundNetworkBlocked extends DriverError {
  const OutboundNetworkBlocked(super.message);
}

/// A logical name in a feature has no entry in tests/drivers/operations.dart: a defect of the test, not a missing feature.
class NotMapped extends DriverError {
  NotMapped(String kind, String name, Iterable<String> known)
      : super("NotMapped: no $kind named '$name' in tests/drivers/operations.dart (known: ${(known.toList()..sort()).join(', ')})");
}

/// A step of a feature that no step definition matches, or that more than one matches: a defect of the test.
class StepError extends DriverError {
  const StepError(super.message);
}
