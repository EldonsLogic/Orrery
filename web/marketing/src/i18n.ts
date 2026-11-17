import ar from '../messages/ar.json';
import en from '../messages/en.json';

export const locales = ['ar', 'en'] as const;
export type Locale = (typeof locales)[number];
export const defaultLocale: Locale = 'ar';
export const messages = { ar, en } as const;
export const directionOf = (l: Locale) => (l === 'ar' ? 'rtl' : 'ltr');
export const isLocale = (v: string): v is Locale => (locales as readonly string[]).includes(v);
