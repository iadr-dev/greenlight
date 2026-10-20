// Errors the drivers throw. The marker in ExpectedMissing is what the red gate classifies on.
export const MARKER = 'BDD_EXPECTED_MISSING';

/** The system under test does not have this yet. During the red phase this is the right failure. */
export class ExpectedMissing extends Error {
  constructor(what: string) {
    super(`${MARKER}: ${what} does not exist yet`);
  }
}

/** The page called an external dependency that the scenario did not stub. */
export class UnstubbedCall extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'UnstubbedCall';
  }
}

/** A real connection to a host outside the application was attempted. Stub the dependency instead. */
export class OutboundNetworkBlocked extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'OutboundNetworkBlocked';
  }
}

/** A logical name in a feature has no entry in tests/drivers/operations.ts: a defect of the test, not a missing feature. */
export class NotMapped extends Error {
  constructor(kind: string, name: string, known: Iterable<string>) {
    super(`NotMapped: no ${kind} named '${name}' in tests/drivers/operations.ts (known: ${[...known].sort((a, b) => a.localeCompare(b)).join(', ')})`);
  }
}
