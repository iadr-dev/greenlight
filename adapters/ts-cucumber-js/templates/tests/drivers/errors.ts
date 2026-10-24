// Errors the drivers throw. The marker in ExpectedMissing is what the red gate classifies on.
export const MARKER = 'BDD_EXPECTED_MISSING';

/** An error that reports its class name as its name, so the JUnit report shows `OutboundNetworkBlocked`, not `Error`. */
abstract class DriverError extends Error {
  constructor(message: string) {
    super(message);
    this.name = new.target.name;
  }
}

/** The system under test does not have this yet. During the red phase this is the right failure. */
export class ExpectedMissing extends DriverError {
  constructor(what: string) {
    super(`${MARKER}: ${what} does not exist yet`);
  }
}

/** The system called an external dependency that the scenario did not stub. */
export class UnstubbedCall extends DriverError {}

/** A real network connection was attempted. Stub the dependency instead. */
export class OutboundNetworkBlocked extends DriverError {}

/** A logical name in a feature has no entry in tests/drivers/operations.ts: a defect of the test, not a missing feature. */
export class NotMapped extends DriverError {
  constructor(kind: string, name: string, known: Iterable<string>) {
    super(`NotMapped: no ${kind} named '${name}' in tests/drivers/operations.ts (known: ${[...known].sort().join(', ')})`);
  }
}
