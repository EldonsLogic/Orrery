import type { Loc } from './types';

/** Picks the label for a locale; falls back to English, then to the id, so a missing label never blanks a screen. */
export const pick = (labels: Loc | undefined, locale: string, fallback: string): string =>
  labels?.[locale] ?? labels?.en ?? fallback;
