import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import data from './colour.data.json';
import { BASE, derive, normHex, rawPairs } from './colour';

const S = data.samples;

const root = resolve(__dirname, '../../../../..');
const py = (colour: string) =>
  JSON.parse(execFileSync('python3', ['-B', resolve(root, 'docs/brand/tools/derive_tenant_theme.py'), colour, '--json'], { cwd: resolve(root, 'docs/brand/tools'), encoding: 'utf8' }).toString());
const pyRun = (colour: string) => {
  try {
    return py(colour);
  } catch (e) {
    const out = (e as { stdout?: string }).stdout; // exit 1 = rejected, JSON still printed
    if (out) return JSON.parse(out);
    throw e;
  }
};

describe('base colours', () => {
  it('match docs/brand/tokens/tokens.json', () => {
    const c = JSON.parse(readFileSync(resolve(root, 'docs/brand/tokens/tokens.json'), 'utf8')).color;
    for (const m of ['light', 'dark'] as const) for (const k of Object.keys(BASE[m]) as Array<keyof (typeof BASE)['light']>) expect(BASE[m][k]).toBe(c[m][k].hex);
  });
});

describe('derive (parity with docs/brand/tools/derive_tenant_theme.py)', () => {
  it.each(S.parity)('%s', (c) => {
    const ref = pyRun(c);
    const mine = derive(c);
    expect(mine.status).toBe(ref.status);
    if (mine.status !== 'ok') return;
    expect(mine.light.primary).toBe(ref.light.primary);
    expect(mine.dark.primary).toBe(ref.dark.primary);
    for (const m of ['light', 'dark'] as const) {
      const refPairs = new Map<string, { ratio: number }>((ref.pairs[m] as Array<{ id: string; ratio: number }>).map((p) => [p.id, p]));
      for (const p of mine[m].pairs) {
        expect(refPairs.get(p.id)?.ratio).toBeCloseTo(p.ratio, 2);
        expect(p.ok).toBe(true);
      }
    }
  });
});

describe('derive', () => {
  it('rejects bad input with a code', () => {
    expect(derive('zzz')).toEqual({ status: 'rejected', code: 'invalid' });
    expect(derive(S.shortGrey)).toEqual({ status: 'rejected', code: 'grey' });
    expect(derive(S.danger)).toEqual({ status: 'rejected', code: 'danger' });
  });
  it('reports the raw colour honestly when it fails AA', () => {
    const r = rawPairs(S.pale);
    expect(r?.light.some((p) => !p.ok)).toBe(true);
    expect(rawPairs('nope')).toBeNull();
  });
  it('normalises short hex', () => expect(normHex(S.short)).toBe(S.shortNorm));
});
