'use client';

import { useState, type ReactNode } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import Link from 'next/link';
import { ArrowDown, ArrowUp, TriangleAlert } from 'lucide-react';
import type { Locale } from '../../i18n';
import { Badge, Button, Card, Mark } from '../../ui';
import { cx } from '../../ui/cx';
import button from '../../ui/Button.module.css';
import { formatNumber } from '../../lib/format';
import { ProgressMarks } from '../marks/ProgressMarks';
import { StatusMark } from '../marks/StatusMark';
import { LoadingMark } from '../marks/LoadingMark';
import type { Activity, HomeOverview, Kpi, Money, TodayFacts } from '../../home/types';
import styles from './Home.module.css';

// One digit system per view (latn), and the currency code as a small muted label after the figure.
const NS = 'latn';
const brand = (c: ReactNode) => <bdi>{c}</bdi>;
// Document numbers never break at their hyphen (non-breaking hyphen), in either direction.
const keep = (ref: string) => ref.replace(/-/g, '‑');

function Amount({ value, locale, className }: { value: Money; locale: Locale; className?: string }) {
  const t = useTranslations('home.currency');
  return (
    <span className={cx(styles.amount, className)}>
      <bdi className={styles.figure}>{formatNumber(locale, Math.round(value.amount), NS)}</bdi>
      <span className={styles.currency}>{t.has(value.currency) ? t(value.currency) : value.currency}</span>
    </span>
  );
}

/** Six month-ends, no axes, low emphasis. Decorative: the figure and the change beside it carry the meaning. SVG coordinates never mirror, so time runs left to right in both languages. */
export function Sparkline({ values }: { values: ReadonlyArray<number> }) {
  const w = 96;
  const h = 32;
  const min = Math.min(...values);
  const span = Math.max(...values) - min || 1;
  const pts = values.map((v, i) => `${((i / (values.length - 1)) * w).toFixed(1)},${(h - 2 - ((v - min) / span) * (h - 4)).toFixed(1)}`);
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className={styles.spark} aria-hidden="true" focusable="false">
      <polyline points={pts.join(' ')} fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

function KpiTile({ kpi, locale }: { kpi: Kpi; locale: Locale }) {
  const t = useTranslations('home.kpis');
  const up = (kpi.change ?? 0) >= 0;
  return (
    <li className={styles.tile}>
      <div className={styles.tileHead}>
        <span className={styles.tileLabel}>{t(kpi.id)}</span>
        {kpi.trend ? <Sparkline values={kpi.trend} /> : null}
      </div>
      <div className={styles.tileValue}>
        {'count' in kpi.value ? (
          <span className={styles.kpiValue}>
            <bdi className={styles.figure}>{formatNumber(locale, kpi.value.count, NS)}</bdi>
          </span>
        ) : (
          <Amount value={kpi.value} locale={locale} className={styles.kpiValue} />
        )}
      </div>
      <div className={styles.tileFoot}>
        {kpi.change !== undefined ? (
          <>
            <Badge tone={up ? 'success' : 'danger'} icon={up ? <ArrowUp className={styles.icon} /> : <ArrowDown className={styles.icon} />}>
              {t(up ? 'up' : 'down', { value: formatNumber(locale, Math.abs(kpi.change), NS) })}
            </Badge>
            <span className={styles.caption}>{t('vsLast')}</span>
          </>
        ) : null}
        {kpi.overdue ? (
          <Badge tone="warning" icon={<TriangleAlert className={styles.icon} />}>
            {t('overdue', { count: formatNumber(locale, kpi.overdue, NS) })}
          </Badge>
        ) : null}
        {kpi.oldestDays ? <span className={styles.caption}>{t('oldest', { days: kpi.oldestDays })}</span> : null}
      </div>
    </li>
  );
}

function Today({ facts, locale }: { facts: TodayFacts; locale: Locale }) {
  const t = useTranslations('home.today');
  return (
    <Card as="section" aria-labelledby="today-title" className={styles.panel}>
      <h2 id="today-title" className={styles.sectionTitle}>
        {t('title')}
      </h2>
      <dl className={styles.facts}>
        <div className={styles.fact}>
          <dt>{t('deliveries')}</dt>
          <dd>
            <bdi className={cx(styles.figure, styles.factFigure)}>{formatNumber(locale, facts.deliveries, NS)}</bdi>
          </dd>
        </div>
        {(['collections', 'payments'] as const).map((k) => (
          <div key={k} className={styles.fact}>
            <dt>
              {t(k)}
              <span className={styles.factNote}>{t('count', { count: facts[k].count })}</span>
            </dt>
            <dd>
              <Amount value={facts[k]} locale={locale} className={styles.factFigure} />
            </dd>
          </div>
        ))}
      </dl>
    </Card>
  );
}

const dayKey = (iso: string) => iso.slice(0, 10);

function ActivityList({ items, asOf, locale }: { items: ReadonlyArray<Activity>; asOf: string; locale: Locale }) {
  const t = useTranslations('home.activity');
  const time = new Intl.DateTimeFormat(locale, { hour: '2-digit', minute: '2-digit', hourCycle: 'h23', numberingSystem: NS, timeZone: 'UTC' } as Intl.DateTimeFormatOptions);
  const days = [...new Set(items.map((a) => dayKey(a.at)))];
  return (
    <Card as="section" aria-labelledby="activity-title" className={styles.panel}>
      <h2 id="activity-title" className={styles.sectionTitle}>
        {t('title')}
      </h2>
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
                    <span>{t.rich(`kind.${a.kind}`, { brand, ref: keep(a.ref ?? ''), party: a.party?.[locale] ?? '', count: a.count ?? 0 })}</span>
                    {a.amount ? <Amount value={a.amount} locale={locale} /> : null}
                  </span>
                </li>
              ))}
          </ol>
        </div>
      ))}
    </Card>
  );
}

/** The owner's home: greeting, Ask Seshna, the build journey if not live, the month's figures, approvals, today and activity. */
export function HomeScreen({ data, loading = false, company, person }: { data: HomeOverview | null; loading?: boolean; company: string; person: string }) {
  const t = useTranslations('home');
  const tc = useTranslations('chat.suggestions.owner');
  const locale = useLocale() as Locale;
  const [question, setQuestion] = useState('');
  const live = data?.buildState === 'live';
  const date = data
    ? new Intl.DateTimeFormat(locale, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric', calendar: 'gregory', numberingSystem: NS, timeZone: 'UTC' } as Intl.DateTimeFormatOptions).format(new Date(`${data.asOf}T00:00:00Z`))
    : null;

  return (
    <section aria-labelledby="home-title" className={styles.home}>
      <div className={styles.hero}>
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

        {/* The chat screen owns the conversation; this entry takes the owner there. The input has no name, so the question
            never lands in the URL. Handing it to the chat composer is a follow-up (WEB-026 composer). */}
        <form className={styles.ask} action="/chat/" method="get" role="search" aria-labelledby="ask-title">
          <label id="ask-title" htmlFor="ask-input" className={styles.askLabel}>
            <Mark tone="accent" upper="solid" lower="outline" size={20} />
            <span>{t.rich('ask.title', { brand })}</span>
          </label>
          <div className={styles.askField}>
            <input id="ask-input" className={styles.askInput} value={question} onChange={(e) => setQuestion(e.target.value)} placeholder={t('ask.placeholder')} autoComplete="off" />
            <Button type="submit" className={styles.askButton}>
              <span>{t('ask.submit')}</span>
              <ArrowUp aria-hidden="true" />
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
          <p className={styles.caption}>{t.rich('ask.hint', { brand })}</p>
        </form>
      </div>

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

      {data && (data.kpis.length > 0 || data.activity.length > 0) ? (
        <div className={styles.columns}>
          {data.kpis.length > 0 ? (
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
                        <Amount value={a.amount} locale={locale} className={styles.rowAmount} />
                        <Link href="/chat/" className={cx(button.root, button.secondary, button.sm, styles.review)} aria-label={t('approvals.reviewLabel', { item: title })}>
                          {t('approvals.review')}
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              )}
            </Card>
          ) : null}
          <div className={styles.side}>
            {live && data.today ? <Today facts={data.today} locale={locale} /> : null}
            {data.activity.length > 0 ? <ActivityList items={data.activity} asOf={data.asOf} locale={locale} /> : null}
          </div>
        </div>
      ) : loading ? (
        <LoadingMark label={t('loading')} />
      ) : null}
    </section>
  );
}
