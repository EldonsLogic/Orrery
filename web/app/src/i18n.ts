import ar from '../messages/ar.json';
import en from '../messages/en.json';

export const locales = ['ar', 'en'] as const;
export type Locale = (typeof locales)[number];
export const defaultLocale: Locale = 'ar';
export const messages = { ar, en } as const;

export type Direction = 'rtl' | 'ltr';
export const directionOf = (locale: Locale): Direction => (locale === 'ar' ? 'rtl' : 'ltr');

export const isLocale = (v: unknown): v is Locale => typeof v === 'string' && (locales as readonly string[]).includes(v);
