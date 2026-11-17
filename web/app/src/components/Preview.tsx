'use client';

import { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { useSettings } from './Providers';
import { useTheme } from '../lib/useTheme';
import { formatDate, formatNumber } from '../lib/format';
import { locales, type Direction } from '../i18n';
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
    </main>
  );
}
