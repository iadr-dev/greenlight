// Running a command by its logical name in the scenario workspace.
//
// The table of a `runs` step has two columns, key and value. Keys: `arg` (repeat for several arguments), `stdin`, and
// `env.NAME`.
import { strict as assert } from 'node:assert';
import { spawnSync } from 'node:child_process';
import type { DataTable } from '@cucumber/cucumber';
import { NotMapped } from './errors';
import { COMMANDS } from './operations';
import type { GreenlightWorld } from './world';

const TIMEOUT_MS = 60_000;

export function run(world: GreenlightWorld, command: string, table: DataTable | undefined): void {
  const mapped = COMMANDS[command];
  if (mapped === undefined) {
    throw new NotMapped('command', command, Object.keys(COMMANDS));
  }
  const [program = '', ...words] = mapped;
  const env: NodeJS.ProcessEnv = { ...process.env };
  let stdin: string | undefined;
  for (const [key = '', value = ''] of (table?.raw() ?? []).slice(1)) {
    if (key === 'arg') {
      words.push(value);
    } else if (key === 'stdin') {
      stdin = value;
    } else if (key.startsWith('env.')) {
      env[key.slice(4)] = value;
    } else {
      assert.fail(`unknown key '${key}' in the command table (use arg, stdin or env.NAME)`);
    }
  }
  const done = spawnSync(program, words, { cwd: world.workspace.root, input: stdin, env, encoding: 'utf-8', timeout: TIMEOUT_MS });
  if (done.error) {
    throw done.error;
  }
  world.outcome = { kind: 'cli', exitCode: done.status ?? -1, stdout: done.stdout, stderr: done.stderr };
}

export function assertSucceeds(world: GreenlightWorld): void {
  const outcome = world.last('cli');
  assert.equal(outcome.exitCode, 0, `the command should succeed but exited ${outcome.exitCode}: ${outcome.stderr.trim()}`);
}

export function assertFails(world: GreenlightWorld, error: string): void {
  const outcome = world.last('cli');
  assert.notEqual(outcome.exitCode, 0, 'the command should fail but it succeeded');
  assert.ok(world.matchesError(outcome, error), `the command failed, but not with '${error}': exit ${outcome.exitCode}, ${outcome.stderr.trim()}`);
}
