// An isolated workspace per scenario, with files addressed by logical name.
import { strict as assert } from 'node:assert';
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync, existsSync, statSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve, sep } from 'node:path';
import { assertTextContains } from './compare';
import { NotMapped } from './errors';
import { FILES } from './operations';

export class Workspace {
  readonly root = resolve(mkdtempSync(join(tmpdir(), 'greenlight-')));

  path(name: string): string {
    const mapped = FILES[name];
    if (mapped === undefined) {
      throw new NotMapped('file', name, Object.keys(FILES));
    }
    const target = resolve(this.root, mapped);
    assert.ok(target.startsWith(this.root + sep), `'${name}' maps outside the workspace`);
    return target;
  }

  write(name: string, content: string): void {
    const target = this.path(name);
    mkdirSync(dirname(target), { recursive: true });
    writeFileSync(target, content, { encoding: 'utf-8' });
  }

  read(name: string): string {
    const target = this.path(name);
    assert.ok(existsSync(target) && statSync(target).isFile(), `the file '${name}' (${FILES[name]}) was not produced`);
    return readFileSync(target, 'utf-8');
  }

  assertContains(name: string, expected: string): void {
    assertTextContains(this.read(name), expected, `the file '${name}'`);
  }

  remove(): void {
    rmSync(this.root, { recursive: true, force: true });
  }
}
