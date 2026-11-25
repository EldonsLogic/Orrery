// BRD-014: the product name stays Latin in every language and is isolated where it sits in mixed-direction text.
import { describe, expect, it } from 'vitest';
import appAr from '../messages/ar.json';
import appEn from '../messages/en.json';
import mktAr from '../../marketing/messages/ar.json';
import mktEn from '../../marketing/messages/en.json';
import { composeTitle } from './components/RouteTitle';

const strings = (o: unknown): string[] =>
  typeof o === 'string' ? [o] : o && typeof o === 'object' ? Object.values(o).flatMap(strings) : [];

const ARABIC = '\\u0600-\\u06FF\\u0750-\\u077F\\u08A0-\\u08FF\\uFB50-\\uFDFF\\uFE70-\\uFEFF';
// Arabic letters directly touching the name, or the common Arabic transliterations of it.
const BAD = [new RegExp(`[${ARABIC}]Seshna|Seshna[${ARABIC}]`, 'i'), /سيشنا|سشنا|سيشنه|سشنه/];

describe.each([
  ['app en', appEn],
  ['app ar', appAr],
  ['marketing en', mktEn],
  ['marketing ar', mktAr],
])('%s messages', (_name, msgs) => {
  it('never writes the product name in Arabic script or glued to Arabic letters', () => {
    expect(strings(msgs).filter((s) => BAD.some((re) => re.test(s)))).toEqual([]);
  });
});

describe('scan patterns', () => {
  it('catch the spellings they are meant to catch', () => {
    for (const s of ['مرحبا بك في سيشنا', 'سشنا', 'منصةSeshna']) expect(BAD.some((re) => re.test(s))).toBe(true);
    for (const s of ['مرحبا بك في Seshna', 'Seshna']) expect(BAD.some((re) => re.test(s))).toBe(false);
  });
});

describe('composeTitle', () => {
  it('isolates the Latin name in an Arabic page title', () => {
    expect(composeTitle('المحادثة', 'Seshna')).toBe('المحادثة | ⁨Seshna⁩');
    expect(composeTitle(null, 'Seshna')).toBe('⁨Seshna⁩');
  });
});
