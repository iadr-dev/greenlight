// The map from the logical names used in features to this system. Features never contain URLs, binaries or module paths.
// The step-engineer fills this in from the system map (system.md); the sample entries below belong to the sample feature
// and can be deleted with it.
import { add } from '../sample/domain';

export interface Api {
  method: string;
  path: string;          // may contain {field}, filled from the request data
}

/** What a logical error looks like. Any field that is set must match. */
export interface ErrorRule {
  statuses?: number[];         // HTTP status codes
  exception?: string;          // the name of the error class
  exitCode?: number;           // process exit code
  text?: string;               // text in the response body, stderr or the error message
}

export const API: Record<string, Api> = {
  // 'place order': { method: 'POST', path: '/orders' },
};

export const COMMANDS: Record<string, string[]> = {
  // 'export report': ['node', 'dist/cli.js', 'export'],
};

/** A library operation is a function the tests import: called with an object (named arguments), a list (positional
 *  arguments) or a single value. Import the application's modules above and map the logical names here. */
export const LIB: Record<string, (...args: never[]) => unknown> = {
  add: ({ a, b }: { a: number; b: number }) => add(a, b),        // sample
};

export const FILES: Record<string, string> = {
  // report: 'out/report.txt',            // relative to the scenario workspace
};

export const ERRORS: Record<string, ErrorRule> = {
  'negative input': { exception: 'RangeError' },        // sample
  // 'validation error': { statuses: [400, 422] },
};
