'use client';

import { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { useSettings } from './Providers';
import { useTheme } from '../lib/useTheme';
import { formatDate, formatNumber } from '../lib/format';
import { locales, type Direction } from '../i18n';
import {
  Alert,
  Badge,
  Button,
  Card,
  Checkbox,
  DatePicker,
  Select,
  Spinner,
  Stack,
  Table,
  TextField,
} from '../ui';
import styles from './Preview.module.css';

const COLOUR_TOKENS = [
  '--color-background',
  '--color-surface',
  '--color-text',
  '--color-primary',
  '--color-accent',
  '--color-success',
  '--color-warning',
  '--color-danger',
] as const;

const TYPE_STEPS = ['display', 'h1', 'h2', 'h3', 'body', 'small', 'caption'] as const;
const MODES = [
  ['light', 'themeLight'],
  ['dark', 'themeDark'],
  ['system', 'themeSystem'],
] as const;
const DIRECTIONS = [
  ['auto', 'directionAuto'],
  ['rtl', 'directionRtl'],
  ['ltr', 'directionLtr'],
] as const;

const SAMPLE_AMOUNT = 1234567.89;
const SAMPLE_DATE = new Date(Date.UTC(2000, 0, 15));
const SAMPLE_COUNT = 12;

const ICON_PATHS = {
  success: 'M3 8.5l3.5 3.5L13 5l-1.4-1.4L6.5 9.2 4.4 7.1z',
  warning: 'M8 1.5l7 12.5H1zM7.2 6h1.6v4H7.2zm0 5h1.6v1.6H7.2z',
  danger: 'M4.2 2.8L8 6.6l3.8-3.8 1.4 1.4L9.4 8l3.8 3.8-1.4 1.4L8 9.4l-3.8 3.8-1.4-1.4L6.6 8 2.8 4.2z',
  info: 'M7.2 7h1.6v5H7.2zm0-3h1.6v1.6H7.2z',
  neutral: 'M4 7h8v2H4z',
} as const;

function Icon({ kind }: { kind: keyof typeof ICON_PATHS }) {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" fill="currentColor" focusable="false">
      <path d={ICON_PATHS[kind]} />
    </svg>
  );
}

type InvoiceRow = { number: string; customer: string; status: 'success' | 'warning' | 'danger'; amount: number };
const INVOICES: InvoiceRow[] = [
  { number: 'INV-0042', customer: 'Gulf Trading Co.', status: 'success', amount: 12500.5 },
  { number: 'INV-0043', customer: 'Nile Foods', status: 'warning', amount: 980 },
  { number: 'INV-0044', customer: 'Desert Logistics', status: 'danger', amount: 45300.25 },
];

function DatePickerPreview() {
  const t = useTranslations('preview.components.datePicker');
  const { locale, direction } = useSettings();
  const [value, setValue] = useState('2025-06-26');
  const [calendar, setCalendar] = useState<'gregorian' | 'hijri'>('hijri');
  const [weekStart, setWeekStart] = useState(locale === 'ar' ? 6 : 1);
  const [secondary, setSecondary] = useState(true);
  return (
    <Stack gap={2}>
      <h3 className={styles.h3}>{t('title')}</h3>
      <Stack direction="row" wrap align="center">
        <Select label={t('calendarLabel')} value={calendar} onChange={(e) => setCalendar(e.target.value as typeof calendar)}>
          <option value="gregorian">{t('gregorian')}</option>
          <option value="hijri">{t('hijri')}</option>
        </Select>
        <Select label={t('weekStartLabel')} value={weekStart} onChange={(e) => setWeekStart(Number(e.target.value))}>
          {(['6', '0', '1'] as const).map((d) => (
            <option key={d} value={d}>{t(`days.${d}`)}</option>
          ))}
        </Select>
        <Checkbox label={t('secondary')} checked={secondary} onChange={(e) => setSecondary(e.target.checked)} />
      </Stack>
      <DatePicker
        label={t('dueLabel')}
        hint={t('dueHint')}
        value={value}
        onChange={setValue}
        calendar={calendar}
        locale={locale}
        dir={direction}
        weekStart={weekStart}
        secondary={secondary}
        numberSystem={locale === 'ar' ? 'arab' : 'latn'}
        labels={{
          openCalendar: t('openCalendar'),
          previousMonth: t('previousMonth'),
          nextMonth: t('nextMonth'),
          calendarDialog: t('calendarDialog'),
          invalidError: t('invalidError'),
          ambiguousError: t('ambiguousError'),
        }}
      />
      <span>
        {t('stored')} <bdi dir="ltr">{value || t('none')}</bdi>
      </span>
    </Stack>
  );
}

function ComponentsPreview() {
  const t = useTranslations('preview.components');
  const { locale } = useSettings();
  const required = t('fields.required');
  return (
    <section>
      <h2 className={styles.h2}>{t('title')}</h2>
      <p>{t('intro')}</p>
      <Stack gap={4}>
        <Stack gap={1}>
          <h3 className={styles.h3}>{t('buttons.title')}</h3>
          <Stack direction="row" wrap align="center">
            <Button variant="primary">{t('buttons.primary')}</Button>
            <Button variant="secondary">{t('buttons.secondary')}</Button>
            <Button variant="danger">{t('buttons.danger')}</Button>
            <Button variant="ghost">{t('buttons.ghost')}</Button>
            <Button size="sm">{t('buttons.small')}</Button>
            <Button size="lg">{t('buttons.large')}</Button>
            <Button loading>{t('buttons.loading')}</Button>
            <Button disabled>{t('buttons.disabled')}</Button>
          </Stack>
        </Stack>

        <Stack gap={2}>
          <h3 className={styles.h3}>{t('fields.title')}</h3>
          <TextField label={t('fields.textLabel')} hint={t('fields.textHint')} required requiredMark={required} />
          <TextField label={t('fields.errorLabel')} type="email" defaultValue="owner@" error={t('fields.errorText')} />
          <TextField label={t('fields.numericLabel')} hint={t('fields.numericHint')} numeric defaultValue="1234567.89" />
          <Select label={t('fields.selectLabel')} hint={t('fields.selectHint')} defaultValue="net30">
            <option value="net30">{t('fields.optionNet30')}</option>
            <option value="net60">{t('fields.optionNet60')}</option>
            <option value="cash">{t('fields.optionCash')}</option>
          </Select>
          <Checkbox label={t('fields.checkboxLabel')} hint={t('fields.checkboxHint')} defaultChecked />
          <Checkbox label={t('fields.checkboxErrorLabel')} error={t('fields.checkboxErrorText')} />
        </Stack>

        <DatePickerPreview />

        <Stack gap={2}>
          <h3 className={styles.h3}>{t('status.title')}</h3>
          <Stack direction="row" wrap>
            <Badge tone="success" icon={<Icon kind="success" />}>{t('status.success')}</Badge>
            <Badge tone="warning" icon={<Icon kind="warning" />}>{t('status.warning')}</Badge>
            <Badge tone="danger" icon={<Icon kind="danger" />}>{t('status.danger')}</Badge>
            <Badge tone="neutral" icon={<Icon kind="neutral" />}>{t('status.neutral')}</Badge>
          </Stack>
          <Alert tone="info" icon={<Icon kind="info" />} title={t('status.infoTitle')}>{t('status.infoBody')}</Alert>
          <Alert tone="success" icon={<Icon kind="success" />} title={t('status.successTitle')}>{t('status.successBody')}</Alert>
          <Alert tone="warning" icon={<Icon kind="warning" />} title={t('status.warningTitle')}>{t('status.warningBody')}</Alert>
          <Alert tone="danger" icon={<Icon kind="danger" />} title={t('status.dangerTitle')}>{t('status.dangerBody')}</Alert>
        </Stack>

        <Stack gap={2}>
          <h3 className={styles.h3}>{t('cards.title')}</h3>
          <Card as="section" aria-labelledby="preview-card-title">
            <Stack gap={1}>
              <strong id="preview-card-title">{t('cards.cardTitle')}</strong>
              <span>{t('cards.cardBody')}</span>
              <Spinner label={t('cards.spinnerLabel')} />
            </Stack>
          </Card>
        </Stack>

        <Stack gap={2}>
          <h3 className={styles.h3}>{t('table.title')}</h3>
          <Table
            caption={t('table.caption')}
            rows={INVOICES}
            rowKey={(r) => r.number}
            empty={t('table.empty')}
            columns={[
              { key: 'number', header: t('table.colNumber'), rowHeader: true, render: (r) => <bdi>{r.number}</bdi> },
              { key: 'customer', header: t('table.colCustomer'), render: (r) => <bdi>{r.customer}</bdi> },
              {
                key: 'status',
                header: t('table.colStatus'),
                render: (r) => (
                  <Badge tone={r.status} icon={<Icon kind={r.status} />}>{t(`status.${r.status}`)}</Badge>
                ),
              },
              { key: 'amount', header: t('table.colAmount'), numeric: true, render: (r) => formatNumber(locale, r.amount, 'latn') },
            ]}
          />
        </Stack>
      </Stack>
    </section>
  );
}

export function Preview() {
  const t = useTranslations('preview');
  const { locale, setLocale, direction, setDirection } = useSettings();
  const { mode, setMode } = useTheme();
  const [values, setValues] = useState<Record<string, string>>({});

  useEffect(() => {
    document.title = t('title');
  }, [t]);

  // Read the resolved token values from the stylesheet so swatches follow theme changes.
  useEffect(() => {
    const cs = getComputedStyle(document.documentElement);
    setValues(Object.fromEntries(COLOUR_TOKENS.map((n) => [n, cs.getPropertyValue(n).trim()])));
  }, [mode, direction]);

  const digitRow = (label: string, ns: 'latn' | 'arab') => (
    <tr>
      <th scope="row">{label}</th>
      <td>{formatNumber(locale, SAMPLE_AMOUNT, ns)}</td>
      <td>{formatDate(locale, SAMPLE_DATE, ns)}</td>
      <td>{formatNumber(locale, SAMPLE_COUNT, ns)}</td>
    </tr>
  );

  return (
    <main className={styles.page}>
      <h1 className={styles.display}>{t('title')}</h1>
      <p>{t('intro')}</p>

      <section className={styles.controls}>
        <label>
          {t('controls.theme')}
          <select value={mode} onChange={(e) => setMode(e.target.value as typeof mode)}>
            {MODES.map(([v, k]) => (
              <option key={v} value={v}>{t(`controls.${k}`)}</option>
            ))}
          </select>
        </label>
        <label>
          {t('controls.language')}
          <select value={locale} onChange={(e) => setLocale(e.target.value as typeof locale)}>
            {locales.map((l) => (
              <option key={l} value={l}>{t(`language.${l}`)}</option>
            ))}
          </select>
        </label>
        <label>
          {t('controls.direction')}
          <select
            value={direction === (locale === 'ar' ? 'rtl' : 'ltr') ? 'auto' : direction}
            onChange={(e) => setDirection(e.target.value === 'auto' ? null : (e.target.value as Direction))}
          >
            {DIRECTIONS.map(([v, k]) => (
              <option key={v} value={v}>{t(`controls.${k}`)}</option>
            ))}
          </select>
        </label>
      </section>

      <section>
        <h2 className={styles.h2}>{t('colours.title')}</h2>
        <ul className={styles.swatches}>
          {COLOUR_TOKENS.map((name) => (
            <li key={name} className={styles.swatch}>
              <span className={styles.chip} style={{ background: `var(${name})` }} />
              <code dir="ltr">{name}</code>
              <code dir="ltr">{values[name]}</code>
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h2 className={styles.h2}>{t('type.title')}</h2>
        {TYPE_STEPS.map((step) => (
          <p key={step} className={styles[`type_${step}`]}>
            {t(`type.${step}`)}: {t('type.sample')}
          </p>
        ))}
      </section>

      <section>
        <h2 className={styles.h2}>{t('digits.title')}</h2>
        <table className={styles.table}>
          <thead>
            <tr>
              <th />
              <th scope="col">{t('digits.amountLabel')}</th>
              <th scope="col">{t('digits.dateLabel')}</th>
              <th scope="col">{t('digits.count', { count: SAMPLE_COUNT })}</th>
            </tr>
          </thead>
          <tbody>
            {digitRow(t('digits.western'), 'latn')}
            {digitRow(t('digits.eastern'), 'arab')}
          </tbody>
        </table>
      </section>

      <section>
        <h2 className={styles.h2}>{t('bidi.title')}</h2>
        <p>
          {t.rich('bidi.sample', {
            ref: (chunks) => <bdi className={styles.mono}>{chunks}</bdi>,
            name: (chunks) => <bdi>{chunks}</bdi>,
          })}
        </p>
      </section>

      <ComponentsPreview />
    </main>
  );
}
