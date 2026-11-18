// Pure date logic for DatePicker. Values are always Gregorian ISO (YYYY-MM-DD); Hijri is the
// Umm al-Qura calendar through the platform Intl (no dependency). See calendars-and-locale.md.
export type Calendar = 'gregorian' | 'hijri';
export type Parts = { year: number; month: number; day: number };

const DAY_MS = 86_400_000;
const ISO_RE = /^(\d{4})-(\d{2})-(\d{2})$/;

const pad = (n: number, w: number) => String(n).padStart(w, '0');
const ms = (iso: string) => Date.UTC(+iso.slice(0, 4), +iso.slice(5, 7) - 1, +iso.slice(8, 10));
const isoFromMs = (t: number) => new Date(t).toISOString().slice(0, 10);

let hijriFmt: Intl.DateTimeFormat | undefined;
function hijriFormatter() {
  hijriFmt ??= new Intl.DateTimeFormat('en-u-ca-islamic-umalqura-nu-latn', {
    day: 'numeric',
    month: 'numeric',
    year: 'numeric',
    timeZone: 'UTC',
  });
  return hijriFmt;
}

/** False when this runtime has no Umm al-Qura calendar (Intl would silently fall back to Gregorian). */
export function hijriSupported(): boolean {
  return hijriFormatter().resolvedOptions().calendar === 'islamic-umalqura';
}

export function parseIso(iso: string): Parts | null {
  const m = ISO_RE.exec(iso);
  if (!m) return null;
  const p = { year: +m[1], month: +m[2], day: +m[3] };
  return isoFromMs(Date.UTC(p.year, p.month - 1, p.day)) === iso ? p : null;
}

/** Calendar parts of a Gregorian ISO date in the given calendar, or null. */
export function toParts(iso: string, calendar: Calendar): Parts | null {
  const g = parseIso(iso);
  if (!g) return null;
  if (calendar === 'gregorian') return g;
  if (!hijriSupported()) return null;
  const out: Partial<Parts> = {};
  for (const part of hijriFormatter().formatToParts(new Date(ms(iso)))) {
    if (part.type === 'year' || part.type === 'month' || part.type === 'day') out[part.type] = +part.value;
  }
  return out.year && out.month && out.day ? (out as Parts) : null;
}

const HIJRI_EPOCH_MS = Date.UTC(622, 6, 19);

/** Gregorian ISO for a date in the given calendar, or null when that date does not exist. */
export function toIso(calendar: Calendar, year: number, month: number, day: number): string | null {
  if (month < 1 || month > 12 || day < 1 || day > 31) return null;
  if (calendar === 'gregorian') {
    const iso = `${pad(year, 4)}-${pad(month, 2)}-${pad(day, 2)}`;
    return parseIso(iso) ? iso : null;
  }
  if (day > 30 || !hijriSupported()) return null;
  const estimate = HIJRI_EPOCH_MS + Math.round((year - 1) * 354.36709 + (month - 1) * 29.530588 + (day - 1)) * DAY_MS;
  for (let k = 0; k <= 8; k++) {
    for (const sign of k === 0 ? [1] : [1, -1]) {
      const iso = isoFromMs(estimate + sign * k * DAY_MS);
      const p = toParts(iso, 'hijri');
      if (p && p.year === year && p.month === month && p.day === day) return iso;
    }
  }
  return null;
}

/** Date as YYYY-MM-DD in the given calendar, Latin digits (the typed and stored-looking form). */
export function formatNumeric(iso: string, calendar: Calendar): string {
  const p = toParts(iso, calendar);
  return p ? `${pad(p.year, 4)}-${pad(p.month, 2)}-${pad(p.day, 2)}` : '';
}

export function monthLength(calendar: Calendar, year: number, month: number): number {
  if (calendar === 'gregorian') return new Date(Date.UTC(year, month, 0)).getUTCDate();
  return toIso('hijri', year, month, 30) ? 30 : 29;
}

export function addDays(iso: string, n: number): string {
  return isoFromMs(ms(iso) + n * DAY_MS);
}

/** Move by whole months in the calendar, clamping the day to the target month length. */
export function addMonths(iso: string, n: number, calendar: Calendar): string | null {
  const p = toParts(iso, calendar);
  if (!p) return null;
  const index = p.year * 12 + (p.month - 1) + n;
  const year = Math.floor(index / 12);
  const month = (index % 12) + 1;
  return toIso(calendar, year, month, Math.min(p.day, monthLength(calendar, year, month)));
}

/** ISO dates of every day of the month that contains `iso`, in order. */
export function monthDays(iso: string, calendar: Calendar): string[] {
  const p = toParts(iso, calendar);
  const first = p && toIso(calendar, p.year, p.month, 1);
  if (!p || !first) return [];
  return Array.from({ length: monthLength(calendar, p.year, p.month) }, (_, i) => addDays(first, i));
}

/** Day of week, 0 = Sunday. */
export const weekdayOf = (iso: string) => new Date(ms(iso)).getUTCDay();

export type NavOptions = { rtl: boolean; weekStart: number; calendar: Calendar };

/** Target date for a grid key press, or null when the key does not navigate. */
export function moveFocus(iso: string, key: string, { rtl, weekStart, calendar }: NavOptions): string | null {
  const offset = (weekdayOf(iso) - weekStart + 7) % 7;
  switch (key) {
    case 'ArrowRight':
      return addDays(iso, rtl ? -1 : 1);
    case 'ArrowLeft':
      return addDays(iso, rtl ? 1 : -1);
    case 'ArrowDown':
      return addDays(iso, 7);
    case 'ArrowUp':
      return addDays(iso, -7);
    case 'Home':
      return addDays(iso, -offset);
    case 'End':
      return addDays(iso, 6 - offset);
    case 'PageDown':
      return addMonths(iso, 1, calendar);
    case 'PageUp':
      return addMonths(iso, -1, calendar);
    default:
      return null;
  }
}

/** Arabic-Indic and Persian digits to Latin, Arabic date separators to "/". */
export function normalizeDigits(text: string): string {
  return text
    .replace(/[٠-٩]/g, (c) => String(c.charCodeAt(0) - 0x0660))
    .replace(/[۰-۹]/g, (c) => String(c.charCodeAt(0) - 0x06f0))
    .replace(/[٫٬؍]/g, '/');
}

export type ParseResult =
  | { kind: 'empty' }
  | { kind: 'invalid' }
  | { kind: 'ok'; iso: string; calendar: Calendar }
  | { kind: 'ambiguous'; candidates: string[]; calendar: Calendar };

// Year ranges tell the calendars apart. Hijri tables cover 1300 to 1599 AH here; Gregorian 1700 to 2400.
const HIJRI_YEARS = [1300, 1599] as const;
const GREGORIAN_YEARS = [1700, 2400] as const;
const TRIPLE = /^(\d+)[\s/.,-]+(\d+)[\s/.,-]+(\d+)$/;

/**
 * Typed entry: year first reads as year-month-day; year last reads as day-month or month-day and
 * is reported ambiguous when both readings are real, different dates. Never guesses.
 */
export function parseTyped(text: string): ParseResult {
  const norm = normalizeDigits(text).trim();
  if (!norm) return { kind: 'empty' };
  const m = TRIPLE.exec(norm);
  if (!m) return { kind: 'invalid' };
  const [a, b, c] = [m[1], m[2], m[3]];
  let year: number;
  let readings: Array<[number, number]>; // [month, day]
  if (a.length === 4 && b.length <= 2 && c.length <= 2) {
    year = +a;
    readings = [[+b, +c]];
  } else if (c.length === 4 && a.length <= 2 && b.length <= 2) {
    year = +c;
    readings = [
      [+b, +a],
      [+a, +b],
    ];
  } else return { kind: 'invalid' };
  const calendar: Calendar | null =
    year >= HIJRI_YEARS[0] && year <= HIJRI_YEARS[1]
      ? 'hijri'
      : year >= GREGORIAN_YEARS[0] && year <= GREGORIAN_YEARS[1]
        ? 'gregorian'
        : null;
  if (!calendar) return { kind: 'invalid' };
  const found = new Set<string>();
  for (const [month, day] of readings) {
    const iso = toIso(calendar, year, month, day);
    if (iso) found.add(iso);
  }
  const candidates = [...found];
  if (candidates.length === 0) return { kind: 'invalid' };
  if (candidates.length === 1) return { kind: 'ok', iso: candidates[0], calendar };
  return { kind: 'ambiguous', candidates, calendar };
}
