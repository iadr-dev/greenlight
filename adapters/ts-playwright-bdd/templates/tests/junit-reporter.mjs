// A small JUnit reporter, so that each test case is named after its scenario and nothing else.
//
// Playwright's own JUnit reporter prefixes the names with the titles of the feature and the rule. `bdd classify` finds
// the scenario of a case by its name, and a scenario whose name also occurs in a rule title would be mistaken. A scenario
// outline gives one case per example, named "<outline> › <example title>".
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, relative } from 'node:path';
import { stripVTControlCharacters } from 'node:util';

const EXAMPLE = /^Example #\d+/;
const PLACEHOLDER = /<[^<>]+>/; // an outline whose title has placeholders: its examples are titled with the values
const INVALID_XML = /[^\t\n\r\u0020-\uD7FF\uE000-\uFFFD\u{10000}-\u{10FFFF}]/gu;

const escapeXml = (text) =>
  stripVTControlCharacters(String(text))
    .replaceAll(INVALID_XML, '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');

function caseName(test) {
  const path = test.titlePath();
  const title = path.at(-1) ?? '';
  const parent = path.at(-2);
  const isExample = EXAMPLE.test(title) || (parent !== undefined && PLACEHOLDER.test(parent));
  return isExample && parent !== undefined ? `${parent} › ${title}` : title;
}

function render(test, result) {
  const open = `<testcase name="${escapeXml(caseName(test))}" classname="${escapeXml(relative(process.cwd(), test.location.file).replaceAll('\\', '/'))}" time="${(result.duration / 1000).toFixed(3)}"`;
  if (result.status === 'passed') {
    return `${open}/>`;
  }
  if (result.status === 'skipped') {
    return `${open}><skipped/></testcase>`;
  }
  const errors = result.errors.map((error) => error.stack ?? error.message ?? String(error.value ?? ''));
  const text = errors.join('\n\n') || result.status;
  const message = (result.errors[0]?.message ?? result.status).trim();
  const summary = stripVTControlCharacters(message).split('\n')[0] ?? result.status;
  // `bdd` shows the first line of a failure, so the type attribute carries the summary rather than the status.
  const detail = escapeXml(`${result.status}\n${text}`);
  return `${open}><failure type="${escapeXml(summary)}">${detail}</failure></testcase>`;
}

export default class JunitReporter {
  entries = [];

  printsToStdio() {
    return false;
  }

  onTestEnd(test, result) {
    this.entries.push({ test, result });
  }

  onEnd() {
    const out = process.env.BDD_REPORT;
    if (!out) {
      throw new Error('BDD_REPORT is not set: run the scenarios with `bdd run`, which gives the report file');
    }
    const failures = this.entries.filter(({ result }) => result.status !== 'passed' && result.status !== 'skipped').length;
    const body = this.entries.map(({ test, result }) => render(test, result)).join('\n');
    mkdirSync(dirname(out), { recursive: true });
    writeFileSync(
      out,
      `<?xml version="1.0" encoding="UTF-8"?>\n<testsuites><testsuite name="scenarios" tests="${this.entries.length}" failures="${failures}">\n${body}\n</testsuite></testsuites>\n`,
      'utf8',
    );
  }
}
