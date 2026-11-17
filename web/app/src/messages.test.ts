import { describe, expect, it } from 'vitest';
import appAr from '../messages/ar.json';
import appEn from '../messages/en.json';
import mktAr from '../../marketing/messages/ar.json';
import mktEn from '../../marketing/messages/en.json';

const keys = (o: unknown, p = ''): string[] =>
  Object.entries(o as Record<string, unknown>).flatMap(([k, v]) =>
    typeof v === 'object' && v !== null ? keys(v, `${p}${k}.`) : [`${p}${k}`],
  );

describe.each([
  ['app', appAr, appEn],
  ['marketing', mktAr, mktEn],
])('%s messages', (_name, ar, en) => {
  it('has the same keys in ar and en', () => {
    expect(keys(ar).sort()).toEqual(keys(en).sort());
  });
  it('has no empty strings', () => {
    const all = [...keys(ar).map((k) => k), ...keys(en)];
    expect(all.length).toBeGreaterThan(0);
    const flat = (o: unknown): string[] => JSON.stringify(o).match(/:"[^"]*"/g) ?? [];
    expect(flat(ar).concat(flat(en)).filter((s) => s === ':""')).toEqual([]);
  });
});
