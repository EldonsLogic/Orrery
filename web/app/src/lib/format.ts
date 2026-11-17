import type { Locale } from '../i18n';

export type NumberingSystem = 'latn' | 'arab';

// Numbering system is always explicit so digits never depend on the browser default.
export function formatNumber(locale: Locale, value: number, numberingSystem: NumberingSystem): string {
  return new Intl.NumberFormat(locale, { numberingSystem, maximumFractionDigits: 2 } as Intl.NumberFormatOptions).format(value);
}

export function formatDate(locale: Locale, value: Date, numberingSystem: NumberingSystem): string {
  return new Intl.DateTimeFormat(locale, {
    calendar: 'gregory',
    numberingSystem,
    timeZone: 'UTC',
    dateStyle: 'long',
  } as Intl.DateTimeFormatOptions).format(value);
}
