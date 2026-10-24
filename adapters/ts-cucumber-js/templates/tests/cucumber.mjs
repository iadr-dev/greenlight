// The one place cucumber-js reads its settings from (`bdd run` passes --config tests/cucumber.mjs). The paths are
// relative to the project, which is where the run command starts. The JUnit report is asked for on the command line.
export default {
  paths: ['tests/features/**/*.feature'],
  import: ['tests/steps/**/*.ts'],
  format: [],
  publishQuiet: true,
};
