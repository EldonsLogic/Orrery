// Locale helpers for the viewer view-model. Names of days, months, regions and languages come from Intl,
// so no English word is hard-coded here.
import type { Loc } from './types';

export const pick = (labels: Loc | undefined, locale: string, fallback: string): string => labels?.[locale] ?? labels?.en ?? fallback;

export const joinList = (items: ReadonlyArray<string>, locale: string): string =>
  new Intl.ListFormat(locale, { style: 'long', type: 'conjunction' }).format(items);

const DAY: Readonly<Record<string, number>> = { sun: 7, mon: 1, tue: 2, wed: 3, thu: 4, fri: 5, sat: 6 };
// 2024-01-01 is a Monday, so day n of January 2024 (UTC) is the weekday with that number.
export const dayName = (code: string, locale: string): string => {
  const n = DAY[code];
  return n === undefined ? code : new Intl.DateTimeFormat(locale, { weekday: 'long', timeZone: 'UTC' }).format(new Date(Date.UTC(2024, 0, n)));
};

export const monthDay = (month: number, day: number, locale: string): string =>
  new Intl.DateTimeFormat(locale, { month: 'long', day: 'numeric', timeZone: 'UTC' }).format(new Date(Date.UTC(2024, month - 1, day)));

export const regionName = (code: string, locale: string): string => new Intl.DisplayNames(locale, { type: 'region' }).of(code) ?? code;
export const languageName = (code: string, locale: string): string => new Intl.DisplayNames(locale, { type: 'language' }).of(code) ?? code;

export const numberText = (value: unknown, locale: string, system: string): string => {
  if (typeof value === 'number') return new Intl.NumberFormat(`${locale}-u-nu-${system === 'eastern_arabic' ? 'arab' : 'latn'}`).format(value);
  if (Array.isArray(value)) return value.map(String).join(', ');
  return String(value ?? '');
};
