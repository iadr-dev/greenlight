import { defineConfig } from '@playwright/test';
import { defineBddConfig } from 'playwright-bdd';

// Paths are relative to this file. The generated test files go to .features-gen and are rebuilt on every run.
const testDir = defineBddConfig({
  features: 'features/**/*.feature',
  steps: 'steps/**/*.ts',
  outputDir: '.features-gen',
  examplesTitleFormat: 'Example #<_index_>', // tests/junit-reporter.mjs names the cases of an outline by this
});

export default defineConfig({
  testDir,
  forbidOnly: true,
  retries: 0,
  timeout: 30_000,
  expect: { timeout: 5_000 },
  // tests/run.mjs sets BDD_REPORT to the file `bdd run` asked for; the reporter writes the JUnit report there.
  reporter: [['list'], ['./junit-reporter.mjs']],
  // To start the application for the run, describe it here (this file is bound, so it cannot change later):
  // webServer: { command: 'npm start', url: 'http://localhost:3000', reuseExistingServer: false },
});
