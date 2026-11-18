import { describe, expect, it } from 'vitest';
import { renderToString } from 'react-dom/server';
import { DatePicker, type DatePickerLabels } from './index';
import {
  addMonths,
  formatNumeric,
  hijriSupported,
  monthDays,
  moveFocus,
  normalizeDigits,
  parseTyped,
  toIso,
  toParts,
} from './dateLogic';

const labels: DatePickerLabels = {
  openCalendar: 'Open calendar',
  previousMonth: 'Previous month',
  nextMonth: 'Next month',
  calendarDialog: 'Choose a date',
  invalidError: 'Not a date',
  ambiguousError: 'Ambiguous date',
};
const props = { label: 'Due date', onChange: () => {}, locale: 'en', weekStart: 1, labels };
const html = (node: React.ReactElement) => renderToString(node);

describe('Umm al-Qura support in this runtime', () => {
  it('Intl has islamic-umalqura', () => {
    expect(hijriSupported()).toBe(true);
  });
});

describe('Gregorian entry', () => {
  it('accepts year-first and day-first with an unambiguous day', () => {
    expect(parseTyped('2025-06-26')).toEqual({ kind: 'ok', iso: '2025-06-26', calendar: 'gregorian' });
    expect(parseTyped('26/06/2025')).toEqual({ kind: 'ok', iso: '2025-06-26', calendar: 'gregorian' });
    expect(parseTyped('06/26/2025')).toEqual({ kind: 'ok', iso: '2025-06-26', calendar: 'gregorian' });
    expect(parseTyped('05/05/2025')).toEqual({ kind: 'ok', iso: '2025-05-05', calendar: 'gregorian' });
  });
  it('shows the stored value in the input, Gregorian', () => {
    const out = html(<DatePicker {...props} value="2025-06-26" calendar="gregorian" />);
    expect(out).toContain('value="2025-06-26"');
  });
});

describe('Hijri entry (Umm al-Qura anchors)', () => {
  it('1447-01-01 AH is 2025-06-26', () => {
    expect(parseTyped('1447-01-01')).toEqual({ kind: 'ok', iso: '2025-06-26', calendar: 'hijri' });
    expect(toParts('2025-06-26', 'hijri')).toEqual({ year: 1447, month: 1, day: 1 });
  });
  it('1446-03-15 AH is 2024-09-18, also written day-first', () => {
    expect(parseTyped('1446-03-15')).toEqual({ kind: 'ok', iso: '2024-09-18', calendar: 'hijri' });
    expect(parseTyped('15/03/1446')).toEqual({ kind: 'ok', iso: '2024-09-18', calendar: 'hijri' });
  });
  it('round-trips every day across several years', () => {
    for (const iso of monthDays('2025-01-01', 'gregorian').concat(monthDays('2025-06-26', 'gregorian'), monthDays('2026-03-10', 'gregorian'))) {
      const p = toParts(iso, 'hijri')!;
      expect(toIso('hijri', p.year, p.month, p.day)).toBe(iso);
    }
  });
  it('shows a Gregorian value as Hijri when calendar is hijri', () => {
    const out = html(<DatePicker {...props} value="2025-06-26" calendar="hijri" />);
    expect(out).toContain('value="1447-01-01"');
    expect(formatNumeric('2024-09-18', 'hijri')).toBe('1446-03-15');
  });
  it('a 30th day that does not exist is invalid', () => {
    const month = monthDays('2025-06-26', 'hijri');
    const p = toParts(month[0], 'hijri')!;
    const len = month.length;
    if (len === 29) expect(toIso('hijri', p.year, p.month, 30)).toBeNull();
    else expect(toIso('hijri', p.year, p.month, 30)).not.toBeNull();
    expect([29, 30]).toContain(len);
  });
});

describe('Arabic-Indic digits', () => {
  it('normalises Arabic-Indic, Persian digits and Arabic separators', () => {
    expect(normalizeDigits('٢٠٢٥-٠٦-٢٦')).toBe('2025-06-26');
    expect(normalizeDigits('۱۴۴۷/۰۱/۰۱')).toBe('1447/01/01');
  });
  it('parses Gregorian and Hijri typed with Arabic-Indic digits', () => {
    expect(parseTyped('٢٠٢٥-٠٦-٢٦')).toEqual({ kind: 'ok', iso: '2025-06-26', calendar: 'gregorian' });
    expect(parseTyped('١٤٤٧/٠١/٠١')).toEqual({ kind: 'ok', iso: '2025-06-26', calendar: 'hijri' });
    expect(parseTyped('٢٦٫٠٦٫٢٠٢٥')).toEqual({ kind: 'ok', iso: '2025-06-26', calendar: 'gregorian' });
  });
});

describe('Invalid and ambiguous input', () => {
  it('rejects nonsense, impossible dates and years outside both ranges', () => {
    for (const bad of ['hello', '2025-02-30', '2025-13-01', '31/04/2025', '25-06-26', '1650-01-01', '1447-01-31x', '2025-06']) {
      expect(parseTyped(bad).kind, bad).toBe('invalid');
    }
  });
  it('empty text is empty', () => {
    expect(parseTyped('  ').kind).toBe('empty');
  });
  it('day and month both 12 or below and different is ambiguous, with both readings', () => {
    expect(parseTyped('03/04/2025')).toEqual({ kind: 'ambiguous', candidates: ['2025-04-03', '2025-03-04'], calendar: 'gregorian' });
    const h = parseTyped('03/04/1447');
    expect(h.kind).toBe('ambiguous');
  });
  it('shows an error state when the caller passes one, and wires it to the input', () => {
    const out = html(<DatePicker {...props} value="" calendar="gregorian" error="Not a date" />);
    expect(out).toContain('aria-invalid="true"');
    expect(out).toContain('Not a date');
  });
});

describe('Keyboard navigation', () => {
  const o = { rtl: false, weekStart: 1, calendar: 'gregorian' as const };
  it('arrows move by day and week; left and right swap in rtl', () => {
    expect(moveFocus('2025-06-26', 'ArrowRight', o)).toBe('2025-06-27');
    expect(moveFocus('2025-06-26', 'ArrowLeft', o)).toBe('2025-06-25');
    expect(moveFocus('2025-06-26', 'ArrowDown', o)).toBe('2025-07-03');
    expect(moveFocus('2025-06-26', 'ArrowUp', o)).toBe('2025-06-19');
    expect(moveFocus('2025-06-26', 'ArrowRight', { ...o, rtl: true })).toBe('2025-06-25');
    expect(moveFocus('2025-06-26', 'ArrowLeft', { ...o, rtl: true })).toBe('2025-06-27');
  });
  it('Home and End follow the week start prop', () => {
    expect(moveFocus('2025-06-26', 'Home', o)).toBe('2025-06-23'); // Monday
    expect(moveFocus('2025-06-26', 'End', o)).toBe('2025-06-29'); // Sunday
    expect(moveFocus('2025-06-26', 'Home', { ...o, weekStart: 6 })).toBe('2025-06-21'); // Saturday
    expect(moveFocus('2025-06-26', 'End', { ...o, weekStart: 6 })).toBe('2025-06-27');
  });
  it('PageUp and PageDown move by calendar month, clamping the day', () => {
    expect(moveFocus('2025-01-31', 'PageDown', o)).toBe('2025-02-28');
    expect(moveFocus('2025-03-15', 'PageUp', o)).toBe('2025-02-15');
    expect(moveFocus('2025-06-26', 'PageDown', { ...o, calendar: 'hijri' })).toBe(addMonths('2025-06-26', 1, 'hijri'));
    expect(toParts(addMonths('2025-06-26', 1, 'hijri')!, 'hijri')).toMatchObject({ year: 1447, month: 2, day: 1 });
  });
  it('other keys do not navigate (Enter selects through the native button, Escape closes)', () => {
    expect(moveFocus('2025-06-26', 'Enter', o)).toBeNull();
    expect(moveFocus('2025-06-26', 'Escape', o)).toBeNull();
  });
  it('open grid has grid roles, labelled cells, a roving tab stop and week start from the prop', () => {
    const out = html(<DatePicker {...props} value="2025-06-26" calendar="gregorian" defaultOpen />);
    expect(out).toContain('role="dialog"');
    expect(out).toContain('role="grid"');
    expect(out).toContain('role="gridcell"');
    expect(out).toContain('aria-label="Thursday, June 26, 2025"');
    expect(out.match(/tabindex="0"/g)?.length).toBe(1);
    expect(out).toContain('aria-selected="true"');
    expect(out.indexOf('>Mon<')).toBeLessThan(out.indexOf('>Sun<'));
    const sat = html(<DatePicker {...props} weekStart={6} value="2025-06-26" calendar="gregorian" defaultOpen />);
    expect(sat.indexOf('>Sat<')).toBeLessThan(sat.indexOf('>Sun<'));
  });
  it('hijri grid is labelled in Umm al-Qura and has 29 or 30 days', () => {
    const out = html(<DatePicker {...props} value="2025-06-26" calendar="hijri" defaultOpen />);
    expect(out).toContain('Muharram 1447 AH');
    expect(out.match(/data-iso=/g)?.length).toBeGreaterThanOrEqual(29);
    expect(out.match(/data-iso=/g)?.length).toBeLessThanOrEqual(30);
  });
});

describe('Direction', () => {
  it.each(['rtl', 'ltr'] as const)('sets dir=%s on the root, keeps the input and day numbers ltr, no inline left/right', (dir) => {
    const out = html(<DatePicker {...props} locale={dir === 'rtl' ? 'ar' : 'en'} dir={dir} value="2025-06-26" calendar="hijri" defaultOpen />);
    expect(out).toContain(`dir="${dir}"`);
    expect(out).toMatch(/<input[^>]*dir="ltr"/);
    expect(out).toContain('<bdi dir="ltr">');
    expect(out).not.toMatch(/style="[^"]*(left|right)/);
  });
  it('shows the secondary calendar and Arabic-Indic day numbers on request', () => {
    const out = html(<DatePicker {...props} locale="ar" numberSystem="arab" dir="rtl" secondary value="2025-06-26" calendar="gregorian" defaultOpen />);
    expect(out).toMatch(/١٤٤٧/);
    expect(out).toMatch(/<bdi dir="ltr">[٠-٩]+<\/bdi>/);
  });
});
