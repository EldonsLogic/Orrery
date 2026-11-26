// WEB-029: run the first-paint script against fake storage, document and timers (no jsdom in this repo).
import { afterEach, describe, expect, it, vi } from 'vitest';
import { LOCALE_STORAGE_KEY, PENDING_CLASS, PENDING_TIMEOUT_MS, THEME_FIXTURE, firstPaintScript, releaseLocalePending } from './firstPaint';
import { storageKey } from '../../theme/theme-engine.js';

const THEME_KEY = storageKey(THEME_FIXTURE.tenantId, THEME_FIXTURE.userId);

function run(store: Record<string, string>, opts: { throws?: boolean } = {}) {
  const classes = new Set<string>();
  const attrs: Record<string, string> = {};
  const el = {
    lang: 'ar',
    dir: 'rtl',
    style: {} as Record<string, string>,
    classList: { add: (c: string) => classes.add(c), remove: (c: string) => classes.delete(c) },
    setAttribute: (k: string, v: string) => {
      attrs[k] = v;
    },
  };
  const localStorage = {
    getItem: (k: string) => {
      if (opts.throws) throw new Error('blocked');
      return store[k] ?? null;
    },
  };
  vi.useFakeTimers();
  new Function('document', 'localStorage', 'setTimeout', firstPaintScript())({ documentElement: el }, localStorage, setTimeout);
  return { el, classes, attrs };
}

afterEach(() => vi.useRealTimers());

describe('firstPaintScript', () => {
  it('applies saved light theme and English before paint and marks pending', () => {
    const { el, classes, attrs } = run({ [THEME_KEY]: 'light', [LOCALE_STORAGE_KEY]: 'en' });
    expect(attrs['data-theme']).toBe('light');
    expect(el.lang).toBe('en');
    expect(el.dir).toBe('ltr');
    expect(classes.has(PENDING_CLASS)).toBe(true);
  });
  it('removes the pending class by itself after the safety timeout', () => {
    const { classes } = run({ [LOCALE_STORAGE_KEY]: 'en' });
    vi.advanceTimersByTime(PENDING_TIMEOUT_MS);
    expect(classes.has(PENDING_CLASS)).toBe(false);
  });
  it('does not hide when the saved locale is the default', () => {
    const { el, classes } = run({ [LOCALE_STORAGE_KEY]: 'ar' });
    expect(classes.size).toBe(0);
    expect(el.dir).toBe('rtl');
  });
  it('leaves everything alone with nothing saved, system theme or an unknown locale', () => {
    const a = run({});
    expect(a.attrs['data-theme']).toBeUndefined();
    expect(a.classes.size).toBe(0);
    const b = run({ [THEME_KEY]: 'system', [LOCALE_STORAGE_KEY]: 'fr' });
    expect(b.attrs['data-theme']).toBeUndefined();
    expect(b.el.lang).toBe('ar');
    expect(b.classes.size).toBe(0);
  });
  it('swallows storage errors', () => {
    expect(() => run({}, { throws: true })).not.toThrow();
  });
  it('releaseLocalePending removes the class', () => {
    const classes = new Set([PENDING_CLASS]);
    releaseLocalePending({ classList: { remove: (c) => classes.delete(c) } });
    expect(classes.size).toBe(0);
  });
});
