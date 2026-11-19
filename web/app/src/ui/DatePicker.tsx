'use client';

import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { cx } from './cx';
import { Field, type FieldMessages } from './Field';
import control from './control.module.css';
import styles from './DatePicker.module.css';
import {
  addMonths,
  formatNumeric,
  monthDays,
  moveFocus,
  parseTyped,
  toParts,
  weekdayOf,
  type Calendar,
} from './dateLogic';

export type { Calendar } from './dateLogic';

/** Every string the picker shows or announces, already translated. */
export type DatePickerLabels = {
  openCalendar: string;
  previousMonth: string;
  nextMonth: string;
  /** Accessible name of the calendar popup. */
  calendarDialog: string;
  invalidError: string;
  ambiguousError: string;
};

export type DatePickerProps = FieldMessages & {
  /** Gregorian ISO date (YYYY-MM-DD) or "". The picker never stores anything else. */
  value: string;
  onChange: (iso: string) => void;
  /** Calendar used to show and grid the date. Typed entry accepts either. */
  calendar: Calendar;
  /** BCP 47 locale for month and weekday names (for example "ar" or "en"). */
  locale: string;
  /** 0 = Sunday ... 6 = Saturday. No market default: the caller passes locale.week.startDay. */
  weekStart: number;
  labels: DatePickerLabels;
  /** Called when typed input is a real date in two readings (day-month or month-day). Nothing is guessed. */
  onAmbiguous?: (info: { text: string; candidates: string[] }) => void;
  /** Show the date in the other calendar as a small line under the field. */
  secondary?: boolean;
  numberSystem?: 'latn' | 'arab';
  dir?: 'rtl' | 'ltr';
  placeholder?: string;
  disabled?: boolean;
  /** Month shown when opened with no value (ISO). Defaults to today. */
  initialView?: string;
  defaultOpen?: boolean;
  className?: string;
};

const UMALQURA = 'islamic-umalqura';
const calId = (c: Calendar) => (c === 'hijri' ? UMALQURA : 'gregory');
const todayIso = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};
const toDate = (iso: string) => new Date(Date.UTC(+iso.slice(0, 4), +iso.slice(5, 7) - 1, +iso.slice(8, 10)));

function Chevron() {
  return (
    <svg className={styles.chevron} viewBox="0 0 16 16" width="16" height="16" fill="currentColor" focusable="false" aria-hidden="true">
      <path d="M10.5 2.6L9.1 1.2 2.3 8l6.8 6.8 1.4-1.4L5.1 8z" />
    </svg>
  );
}

export function DatePicker({
  label,
  hint,
  error,
  requiredMark,
  id,
  className,
  value,
  onChange,
  calendar,
  locale,
  weekStart,
  labels,
  onAmbiguous,
  secondary = false,
  numberSystem = 'latn',
  dir,
  placeholder,
  disabled,
  initialView,
  defaultOpen = false,
}: DatePickerProps) {
  const [text, setText] = useState(() => (value ? formatNumeric(value, calendar) : ''));
  const [status, setStatus] = useState<'ok' | 'invalid' | 'ambiguous'>('ok');
  const [open, setOpen] = useState(defaultOpen);
  const [focusIso, setFocusIso] = useState(value || initialView || '');
  const inputRef = useRef<HTMLInputElement>(null);
  const gridRef = useRef<HTMLTableElement>(null);
  const wantFocus = useRef(false);

  useEffect(() => {
    setText(value ? formatNumeric(value, calendar) : '');
    setStatus('ok');
  }, [value, calendar]);

  useEffect(() => {
    if (!open || !wantFocus.current) return;
    wantFocus.current = false;
    gridRef.current?.querySelector<HTMLElement>('[tabindex="0"]')?.focus();
  }, [open, focusIso]);

  const other: Calendar = calendar === 'hijri' ? 'gregorian' : 'hijri';
  const fmt = (iso: string, cal: Calendar, opts: Intl.DateTimeFormatOptions) =>
    new Intl.DateTimeFormat(`${locale}-u-ca-${calId(cal)}-nu-${numberSystem}`, { ...opts, timeZone: 'UTC' }).format(toDate(iso));

  const commit = () => {
    const r = parseTyped(text);
    if (r.kind === 'empty') {
      setStatus('ok');
      if (value) onChange('');
    } else if (r.kind === 'ok') {
      setStatus('ok');
      setText(formatNumeric(r.iso, calendar));
      if (r.iso !== value) onChange(r.iso);
    } else if (r.kind === 'ambiguous') {
      setStatus('ambiguous');
      onAmbiguous?.({ text, candidates: r.candidates });
    } else setStatus('invalid');
  };

  const choose = (iso: string) => {
    setText(formatNumeric(iso, calendar));
    setStatus('ok');
    setOpen(false);
    if (iso !== value) onChange(iso);
    inputRef.current?.focus();
  };

  const toggle = () => {
    if (open) return setOpen(false);
    setFocusIso(value || initialView || todayIso());
    wantFocus.current = true;
    setOpen(true);
  };

  const step = (n: number) => {
    const next = addMonths(focusIso, n, calendar);
    if (next) setFocusIso(next);
  };

  const onGridKey = (e: KeyboardEvent<HTMLElement>) => {
    if (e.key === 'Escape') {
      e.preventDefault();
      setOpen(false);
      inputRef.current?.focus();
      return;
    }
    if (!gridRef.current?.contains(e.target as Node)) return;
    const rtl = (dir ?? getComputedStyle(e.currentTarget).direction) === 'rtl';
    const next = moveFocus(focusIso, e.key, { rtl, weekStart, calendar });
    if (next) {
      e.preventDefault();
      wantFocus.current = true;
      setFocusIso(next);
    }
  };

  const shown = error ?? (status === 'invalid' ? labels.invalidError : status === 'ambiguous' ? labels.ambiguousError : undefined);
  const days = open && focusIso ? monthDays(focusIso, calendar) : [];
  const lead = days.length ? (weekdayOf(days[0]) - weekStart + 7) % 7 : 0;
  const cells: Array<string | null> = [...Array<null>(lead).fill(null), ...days];
  while (cells.length % 7) cells.push(null);
  const weeks = Array.from({ length: cells.length / 7 }, (_, i) => cells.slice(i * 7, i * 7 + 7));
  const sunday = '2023-01-01';
  const weekdays = Array.from({ length: 7 }, (_, i) => {
    const d = new Date(toDate(sunday).getTime() + ((weekStart + i) % 7) * 86_400_000);
    const iso = d.toISOString().slice(0, 10);
    return { short: fmt(iso, 'gregorian', { weekday: 'short' }), long: fmt(iso, 'gregorian', { weekday: 'long' }) };
  });
  const dayNumber = (n: number) => new Intl.NumberFormat(`${locale}-u-nu-${numberSystem}`).format(n);

  return (
    <Field label={label} hint={hint} error={shown} requiredMark={requiredMark} id={id} className={className}>
      {(wiring) => (
        <div
          className={styles.root}
          dir={dir}
          onBlur={(e) => {
            if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setOpen(false);
          }}
        >
          <div className={styles.row}>
            <input
              {...wiring}
              ref={inputRef}
              type="text"
              dir="ltr"
              inputMode="numeric"
              autoComplete="off"
              placeholder={placeholder}
              disabled={disabled}
              value={text}
              className={cx(control.control, styles.input)}
              onChange={(e) => setText(e.target.value)}
              onBlur={commit}
              onKeyDown={(e) => {
                if (e.key === 'Enter') commit();
                if (e.key === 'ArrowDown' && e.altKey) toggle();
              }}
            />
            <button
              type="button"
              className={styles.toggle}
              aria-label={labels.openCalendar}
              aria-haspopup="dialog"
              aria-expanded={open}
              disabled={disabled}
              onClick={toggle}
            >
              <svg viewBox="0 0 16 16" width="16" height="16" fill="currentColor" focusable="false" aria-hidden="true">
                <path d="M4 1h1.5v1.5h5V1H12v1.5h1.5v12h-11v-12H4zM4 6v7h8V6z" />
              </svg>
            </button>
          </div>
          {secondary && value ? (
            <div className={styles.secondary}>
              <bdi>{fmt(value, other, { day: 'numeric', month: 'long', year: 'numeric' })}</bdi>
            </div>
          ) : null}
          {open && days.length ? (
            <div role="dialog" aria-label={labels.calendarDialog} className={styles.popup} onKeyDown={onGridKey}>
              <div className={styles.header}>
                <button type="button" className={styles.nav} aria-label={labels.previousMonth} onClick={() => step(-1)}>
                  <Chevron />
                </button>
                <div className={styles.title} aria-live="polite">
                  <bdi>{fmt(focusIso, calendar, { month: 'long', year: 'numeric' })}</bdi>
                </div>
                <button type="button" className={cx(styles.nav, styles.next)} aria-label={labels.nextMonth} onClick={() => step(1)}>
                  <Chevron />
                </button>
              </div>
              <table
                ref={gridRef}
                role="grid"
                aria-label={fmt(focusIso, calendar, { month: 'long', year: 'numeric' })}
                className={styles.grid}
              >
                <thead>
                  <tr>
                    {weekdays.map((w) => (
                      <th key={w.long} scope="col" abbr={w.long} className={styles.weekday}>
                        {w.short}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {weeks.map((week, wi) => (
                    <tr key={wi}>
                      {week.map((iso, di) => {
                        if (!iso) return <td key={di} />;
                        const parts = toParts(iso, calendar);
                        const selected = iso === value;
                        return (
                          <td key={iso} role="gridcell" aria-selected={selected}>
                            <button
                              type="button"
                              data-iso={iso}
                              tabIndex={iso === focusIso ? 0 : -1}
                              aria-label={fmt(iso, calendar, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}
                              className={cx(styles.day, selected && styles.selected)}
                              onClick={() => choose(iso)}
                            >
                              <bdi dir="ltr">{dayNumber(parts?.day ?? 0)}</bdi>
                            </button>
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </div>
      )}
    </Field>
  );
}
