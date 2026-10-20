// Runs Stryker on the production files `bdd mutate` hands over and writes the report `bdd mutate` reads.
//
//   node tests/tools/mutate-ts.mjs --report REPORT --test-command "COMMAND" -- FILE [FILE ...]
//
// Started by `bdd mutate` from the project root. COMMAND is the project's own test command (for example `npm test`, or
// `node tests/run.mjs --tag FEAT-007 --out junit.xml`); Stryker's command runner starts it once per mutant and an exit
// status other than 0 means the mutant was noticed. The report is
//
//   {"killed": N, "survived": N, "timeout": N, "suspicious": N, "skipped": N}
//
// The exit status is 0 whenever Stryker ran to the end, survivors or not; 2 when the arguments are refused; 3 when Stryker
// could not run or wrote nothing usable. A mutant no test reached ("NoCoverage") counts as survived; a mutant that broke
// the run for another reason than a failing test ("RuntimeError") is suspicious; neither doubt counts as a kill.
//
// Stryker is a development tool of the project, not of greenlight: install it (`npm install --save-dev
// @stryker-mutator/core`), pinned. Node's standard library only.
import { spawnSync } from 'node:child_process';
import { existsSync, mkdtempSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { isAbsolute, join, relative, resolve, sep } from 'node:path';
import { pathToFileURL } from 'node:url';

export const EXIT_REFUSED = 2;
export const EXIT_TOOL_FAILED = 3;
const SUFFIXES = ['.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs'];
const STRYKER_LOCATIONS = ['node_modules', join('tests', 'node_modules')];

export function checkFiles(root, names) {
  if (names.length === 0) {
    throw new Error('no file to mutate was given');
  }
  const base = resolve(root);
  return [...new Set(names.map((name) => {
    if (isAbsolute(name) || name.split(/[\\/]/).includes('..')) {
      throw new Error(`${name}: give the file relative to the project, without ..`);
    }
    const target = resolve(base, name);
    if (!target.startsWith(base + sep)) {
      throw new Error(`${name}: not inside the project`);
    }
    if (!SUFFIXES.some((suffix) => target.endsWith(suffix)) || !existsSync(target) || !statSync(target).isFile()) {
      throw new Error(`${name}: not an existing script file (${SUFFIXES.join(', ')})`);
    }
    return relative(base, target).split(sep).join('/');
  }))].sort((a, b) => a.localeCompare(b));
}

export function checkReport(root, name) {
  if (!name || !isAbsolute(name)) {
    throw new Error('the report must be an absolute path');
  }
  const target = resolve(name);
  if (target.startsWith(resolve(root) + sep)) {
    throw new Error('the report must not be inside the project');
  }
  return target;
}

export function countsFromReport(report) {
  const counts = { killed: 0, survived: 0, timeout: 0, suspicious: 0, skipped: 0 };
  const place = { Killed: 'killed', Survived: 'survived', NoCoverage: 'survived', Timeout: 'timeout',
    RuntimeError: 'suspicious', CompileError: 'skipped', Ignored: 'skipped' };
  for (const file of Object.values(report.files ?? {})) {
    for (const mutant of file.mutants ?? []) {
      const key = place[mutant.status];
      if (key) {
        counts[key] += 1;
      }
    }
  }
  return counts;
}

export function strykerConfig(files, testCommand, reportFile) {
  return {
    testRunner: 'command',
    commandRunner: { command: testCommand },
    mutate: files,
    reporters: ['json'],
    jsonReporter: { fileName: reportFile },
    coverageAnalysis: 'off',
    cleanTempDir: true,
  };
}

function findStryker(root) {
  for (const place of STRYKER_LOCATIONS) {
    const candidate = join(root, place, '@stryker-mutator', 'core', 'bin', 'stryker.js');
    if (existsSync(candidate)) {
      return candidate;
    }
  }
  throw new Error('Stryker is not installed: npm install --save-dev @stryker-mutator/core');
}

function option(argv, name) {
  const at = argv.indexOf(`--${name}`);
  return at >= 0 ? argv[at + 1] : undefined;
}

function measure(root, files, testCommand) {
  const scratch = mkdtempSync(join(tmpdir(), 'greenlight-stryker-'));
  try {
    const reportFile = join(scratch, 'mutation.json');
    const configFile = join(scratch, 'stryker.config.json');
    writeFileSync(configFile, JSON.stringify(strykerConfig(files, testCommand, reportFile)));
    const done = spawnSync(process.execPath, [findStryker(root), 'run', configFile], { cwd: root, encoding: 'utf8' });
    if (done.error || done.status !== 0 || !existsSync(reportFile)) {
      throw new Error(`Stryker did not finish (status ${done.status}):\n${((done.stdout ?? '') + (done.stderr ?? '')).slice(-3000)}`);
    }
    return countsFromReport(JSON.parse(readFileSync(reportFile, 'utf8')));
  } finally {
    rmSync(scratch, { recursive: true, force: true });
  }
}

function main(argv) {
  const root = process.cwd();
  const separator = argv.indexOf('--');
  let files;
  let report;
  const testCommand = option(argv.slice(0, separator < 0 ? argv.length : separator), 'test-command');
  try {
    if (separator < 0 || !testCommand) {
      throw new Error('usage: node tests/tools/mutate-ts.mjs --report REPORT --test-command "COMMAND" -- FILE [FILE ...]');
    }
    files = checkFiles(root, argv.slice(separator + 1));
    report = checkReport(root, option(argv.slice(0, separator), 'report'));
  } catch (error) {
    console.error(`mutate-ts: ${error.message}`);
    return EXIT_REFUSED;
  }
  try {
    const counts = measure(root, files, testCommand);
    writeFileSync(report, JSON.stringify(counts));
    console.log(`mutate-ts: ${counts.killed} killed, ${counts.survived} survived`);
    return 0;
  } catch (error) {
    console.error(`mutate-ts: ${error.message}`);
    return EXIT_TOOL_FAILED;
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  process.exit(main(process.argv.slice(2)));
}
