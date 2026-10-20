// Runs the scenarios of one feature and writes a JUnit report. Called by `bdd run`:
//   node tests/run.mjs --tag FEAT-007 --out report.xml [--scenario "Scenario name"]
// It generates the test files from the features, then runs Playwright with the settings in tests/bdd.config.ts.
// Both programs are started directly (no shell), from the tooling installed in tests/node_modules.
import { spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const config = join(here, 'bdd.config.ts');
const require = createRequire(import.meta.url);

function option(name) {
  const at = process.argv.indexOf(`--${name}`);
  return at > 0 ? process.argv[at + 1] : undefined;
}

function escapeRegExp(text) {
  return text.replaceAll(/[.*+?^${}()|[\]\\]/g, String.raw`\$&`);
}

function run(program, args, env = process.env) {
  const done = spawnSync(process.execPath, [program, ...args], { stdio: 'inherit', env });
  if (done.error) {
    console.error(`cannot start ${program}: ${done.error.message}`);
    return 1;
  }
  return done.status ?? 1;
}

const tag = option('tag');
const out = option('out');
if (!tag || !out) {
  console.error('usage: node tests/run.mjs --tag FEAT-n --out FILE [--scenario NAME]');
  process.exit(2);
}

// A tag matches whole: FEAT-7 must not select FEAT-70. Tags are part of the title Playwright searches.
const wanted = [String.raw`(?=.*@${escapeRegExp(tag)}(?![\w.-]))`];
const scenario = option('scenario');
if (scenario) {
  wanted.push(`(?=.*${escapeRegExp(scenario)})`);
}

const bddgen = join(dirname(require.resolve('playwright-bdd')), 'cli', 'index.js');
const playwright = require.resolve('@playwright/test/cli');
const generated = run(bddgen, ['-c', config]);
if (generated !== 0) {
  process.exit(generated);
}
process.exit(run(playwright, ['test', '-c', config, '--grep', `^${wanted.join('')}`], { ...process.env, BDD_REPORT: resolve(out) }));
