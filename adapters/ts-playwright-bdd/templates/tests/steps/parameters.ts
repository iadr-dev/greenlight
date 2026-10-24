// The placeholders of the core instructions, as parameter types of the step patterns. They read like the vocabulary
// (`{actor} is signed in as {role}`), and every one is a plain regular expression, so a pattern means what it says.
import { defineParameterType } from 'playwright-bdd';

const text = (name: string, regexp: RegExp): void => defineParameterType({ name, regexp, transformer: (found: string) => found });

text('actor', /[\w.-]+/);
text('target', /[^:\n]+/);           // no colon, so "alice clicks save with:" is not read as a target "save with:"
text('state', /on|off/);
text('mode', /are|include/);
text('action', /clicks|fills|selects|uploads|types|toggles|swipes|scrolls/);
for (const name of ['role', 'entity', 'dependency', 'operation', 'event', 'job', 'flag', 'duration', 'datetime', 'page']) {
  text(name, /.+/);
}
