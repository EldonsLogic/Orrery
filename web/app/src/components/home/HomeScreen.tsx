'use client';

import { useState, type ReactNode } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import Link from 'next/link';
import type { Locale } from '../../i18n';
import { Badge, Button, Card, Mark, VisuallyHidden } from '../../ui';
import control from '../../ui/control.module.css';
import { formatNumber } from '../../lib/format';
import { ProgressMarks } from '../marks/ProgressMarks';
import { StatusMark } from '../marks/StatusMark';
import { LoadingMark } from '../marks/LoadingMark';
import type { Activity, HomeOverview, Kpi, Money } from '../../home/types';
import type { NavItem } from '../../lib/navigation';
import styles from './Home.module.css';

// One digit system per view (latn), and the currency code as a small muted label after the figure.
const NS = 'latn';
const brand = (c: ReactNode) => <bdi>{c}</bdi>;
// Document numbers never break at their hyphen (non-breaking hyphen), in either direction.
const keep = (ref: string) => ref.replace(/-/g, '\u2011');

function Amount({ value, locale, large }: { value: Money; locale: Locale; large?: boolean }) {
  const t = useTranslations('home.currency');
  return (
    <span className={large ? styles.kpiValue : styles.amount}>
      <bdi className={styles.figure}>{formatNumber(locale, Math.round(value.amount), NS)}</bdi>
      <span className={styles.currency}>{t.has(value.currency) ? t(value.currency) : value.currency}</span>
    </span>
  );
}

const Icon = ({ d }: { d: string }) => (
  <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false" className={styles.icon}>
    <path d={d} fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);
const UP = 'M8 13V3M4 7l4-4 4 4';
const DOWN = 'M8 3v10M4 9l4 4 4-4';
const WARN = 'M8 2.5l6 11H2l6-11zM8 7v2.5M8 11.5v.01';

function KpiTile({ kpi, locale }: { kpi: Kpi; locale: Locale }) {
  const t = useTranslations('home.kpis');
  return (
    <li className={styles.tile}>
      <span className={styles.tileLabel}>{t(kpi.id)}</span>
      {'count' in kpi.value ? (
        <span className={styles.kpiValue}>
          <bdi className={styles.figure}>{formatNumber(locale, kpi.value.count, NS)}</bdi>
        </span>
      ) : (
        <Amount value={kpi.value} locale={locale} large />
      )}
      {kpi.change !== undefined ? (
        <span className={styles.delta}>
          <Icon d={kpi.change >= 0 ? UP : DOWN} />
          {t(kpi.change >= 0 ? 'up' : 'down', { value: formatNumber(locale, Math.abs(kpi.change), NS) })}
        </span>
      ) : null}
      {kpi.overdue ? (
        <span className={styles.warning}>
          <Icon d={WARN} />
          {t('overdue', { count: formatNumber(locale, kpi.overdue, NS) })}
        </span>
      ) : null}
      {kpi.oldestDays ? <span className={styles.delta}>{t('oldest', { days: kpi.oldestDays })}</span> : null}
    </li>
  );
}

const dayKey = (iso: string) => iso.slice(0, 10);

function ActivityList({ items, asOf, locale }: { items: ReadonlyArray<Activity>; asOf: string; locale: Locale }) {
  const t = useTranslations('home.activity');
  const time = new Intl.DateTimeFormat(locale, { hour: '2-digit', minute: '2-digit', hourCycle: 'h23', numberingSystem: NS, timeZone: 'UTC' } as Intl.DateTimeFormatOptions);
  const days = [...new Set(items.map((a) => dayKey(a.at)))];
  return (
    <>
      {days.map((day) => (
        <div key={day} className={styles.day}>
          <h3 className={styles.dayHeading}>{day === asOf ? t('today') : t('yesterday')}</h3>
          <ol className={styles.feed}>
            {items
              .filter((a) => dayKey(a.at) === day)
              .map((a) => (
                <li key={a.id} className={styles.feedItem}>
                  <time dateTime={a.at} className={styles.time}>
                    {time.format(new Date(a.at))}
                  </time>
                  <span className={styles.feedText}>
                    <span>
                      {t.rich(`kind.${a.kind}`, {
                        brand,
                        ref: keep(a.ref ?? ''),
                        party: a.party?.[locale] ?? '',
                        count: a.count ?? 0,
                      })}
                    </span>
                    {a.amount ? <Amount value={a.amount} locale={locale} /> : null}
                  </span>
                </li>
              ))}
          </ol>
        </div>
      ))}
    </>
  );
}

/** The owner's home: greeting, Ask Seshna, today or the build journey, the month's figures, approvals and activity. */
export function HomeScreen({
  data,
  loading = false,
  company,
  person,
  shortcuts,
}: {
  data: HomeOverview | null;
  loading?: boolean;
  company: string;
  person: string;
  shortcuts: ReadonlyArray<NavItem>;
}) {
  const t = useTranslations('home');
  const tc = useTranslations('chat.suggestions.owner');
  const locale = useLocale() as Locale;
  const [question, setQuestion] = useState('');
  const live = data?.buildState === 'live';
  const date = data
    ? new Intl.DateTimeFormat(locale, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric', calendar: 'gregory', numberingSystem: NS, timeZone: 'UTC' } as Intl.DateTimeFormatOptions).format(new Date(`${data.asOf}T00:00:00Z`))
    : null;
  // The chat screen owns the conversation; this entry only takes the owner there. The input has no name, so the
  // question never lands in the URL. Handing it to the chat composer is a follow-up (WEB-026 composer).

  return (
    <section aria-labelledby="home-title" className={styles.home}>
      <header className={styles.header}>
        <p className={styles.eyebrow}>
          <span>{company}</span>
          {date ? (
            <>
              <span aria-hidden="true" className={styles.sep} />
              <span>{date}</span>
            </>
          ) : null}
        </p>
        <div className={styles.titleRow}>
          <h1 id="home-title" className={styles.title}>
            {t('greeting', { name: person })}
          </h1>
          {data ? (
            <Badge tone={live ? 'success' : 'neutral'} icon={<Mark upper="solid" lower={live ? 'solid' : 'outline'} size={16} />}>
              {t(live ? 'status.live' : 'status.simulating')}
            </Badge>
          ) : null}
        </div>
      </header>

      <form className={styles.ask} action="/chat/" method="get" role="search" aria-labelledby="ask-title">
        <h2 id="ask-title" className={styles.askTitle}>
          <Mark tone="accent" upper="solid" lower="outline" size={24} />
          <span>{t.rich('ask.title', { brand })}</span>
        </h2>
        <div className={styles.askRow}>
          <VisuallyHidden>
            <label htmlFor="ask-input">{t('ask.label')}</label>
          </VisuallyHidden>
          <input id="ask-input" className={`${control.control} ${styles.askInput}`} value={question} onChange={(e) => setQuestion(e.target.value)} placeholder={t('ask.placeholder')} autoComplete="off" />
          <Button type="submit" size="lg">
            {t('ask.submit')}
          </Button>
        </div>
        <ul className={styles.chips} aria-label={t('ask.suggestions')}>
          {(['cash', 'approvals', 'sales'] as const).map((k) => (
            <li key={k}>
              <Link href="/chat/" className={styles.chip}>
                {tc(k)}
              </Link>
            </li>
          ))}
        </ul>
        <p className={styles.hint}>{t.rich('ask.hint', { brand })}</p>
      </form>

      {live && data?.today ? (
        <section aria-labelledby="today-title" className={styles.today}>
          <h2 id="today-title" className={styles.sectionTitle}>
            {t('today.title')}
          </h2>
          <dl className={styles.facts}>
            <div className={styles.fact}>
              <dt>{t('today.deliveries')}</dt>
              <dd className={styles.factValue}>
                <bdi className={styles.figure}>{formatNumber(locale, data.today.deliveries, NS)}</bdi>
              </dd>
            </div>
            {(['collections', 'payments'] as const).map((k) => (
              <div key={k} className={styles.fact}>
                <dt>{t(`today.${k}`)}</dt>
                <dd className={styles.factValue}>
                  <Amount value={data.today![k]} locale={locale} />
                  <span className={styles.factNote}>{t('today.count', { count: data.today![k].count })}</span>
                </dd>
              </div>
            ))}
          </dl>
        </section>
      ) : null}

      {data && !live ? (
        <Card as="section" aria-labelledby="journey-title" className={styles.journey}>
          <h2 id="journey-title" className={styles.sectionTitle}>
            {t('journey.title')}
          </h2>
          <ProgressMarks buildState={data.buildState} />
          <p className={styles.body}>{t.rich('journey.body', { brand })}</p>
          <Link href="/blueprint/" className={styles.textLink}>
            {t('journey.action')}
          </Link>
        </Card>
      ) : null}

      {data && data.kpis.length > 0 ? (
        <section aria-labelledby="kpi-title">
          <div className={styles.sectionHead}>
            <h2 id="kpi-title" className={styles.sectionTitle}>
              {t('kpis.title')}
            </h2>
            {data.simulated ? <span className={styles.caption}>{t('kpis.simulated')}</span> : null}
          </div>
          <ul role="list" className={styles.tiles} tabIndex={0} aria-labelledby="kpi-title">
            {data.kpis.map((k) => (
              <KpiTile key={k.id} kpi={k} locale={locale} />
            ))}
          </ul>
        </section>
      ) : null}

      {data ? (
      <div className={styles.columns}>
        {data && data.kpis.length > 0 ? (
          <Card as="section" aria-labelledby="approvals-title" className={styles.panel}>
            <div className={styles.panelHead}>
              <h2 id="approvals-title" className={styles.sectionTitle}>
                {t('approvals.title')}
              </h2>
              <p className={styles.caption}>{t.rich('approvals.intro', { brand })}</p>
            </div>
            {data.approvals.length === 0 ? (
              <p className={styles.body}>{t('approvals.empty')}</p>
            ) : (
              <ul role="list" className={styles.rows}>
                {data.approvals.map((a) => {
                  const title = t(`approvals.kind.${a.kind}`, { ref: keep(a.ref) });
                  return (
                    <li key={a.id} className={styles.row}>
                      <div className={styles.rowMain}>
                        <span className={styles.rowTitle}>{title}</span>
                        <span className={styles.rowMeta}>
                          {a.party[locale]} · {a.reason[locale]}
                        </span>
                        <StatusMark status="drafted" size={16} className={styles.rowStatus} />
                      </div>
                      <Amount value={a.amount} locale={locale} />
                      <Link href="/chat/" className={styles.review} aria-label={t('approvals.reviewLabel', { item: title })}>
                        {t('approvals.review')}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            )}
          </Card>
        ) : null}
        {data.activity.length > 0 ? (
          <Card as="section" aria-labelledby="activity-title" className={styles.panel}>
            <h2 id="activity-title" className={styles.sectionTitle}>
              {t('activity.title')}
            </h2>
            <ActivityList items={data.activity} asOf={data.asOf} locale={locale} />
          </Card>
        ) : null}
      </div>
      ) : loading ? (
        <LoadingMark label={t('loading')} />
      ) : null}

      {shortcuts.length > 0 ? (
        <nav aria-labelledby="shortcuts-title" className={styles.shortcuts}>
          <h2 id="shortcuts-title" className={styles.caption}>
            {t('shortcuts')}
          </h2>
          <ul className={styles.chips}>
            {shortcuts.map((s) => (
              <li key={s.id}>
                <Link href={s.href} className={styles.chip}>
                  {s.label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      ) : null}
    </section>
  );
}
