'use client';

import { useId, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { Alert, Badge, Button, Card, Checkbox, Select, TextField } from '../../ui';
import { messagePath, percentText } from '../../approval/labels';
import { submitDecision } from '../../approval/decide';
import type {
  ApprovalPort, CostSection, Detail, DecisionKey, GapsSection, Loc, Money, QuoteLine, ReviewModel, SimulationSection, SummarySection, Totals,
} from '../../approval/types';
import styles from './Approval.module.css';

type Translate = (key: string, values?: Record<string, string | number>) => string;
type Status = { kind: 'idle' } | { kind: 'sending' } | { kind: 'done' } | { kind: 'error'; code: string };

/**
 * Owner approval screen (WEB-027) over the DSC-009 view model. Port-based: decisions leave through `port` only, no
 * network here. All customer- or document-derived text is a React text child (never HTML); sentences are label keys.
 * Not wired to the live host until Q-544 and Q-505 are settled.
 */
export function OwnerApprovalView({ view, port, initialChoice = null }: { view: ReviewModel; port: ApprovalPort; initialChoice?: DecisionKey | null }) {
  const locale = useLocale();
  const t = useTranslations('ownerApproval') as unknown as Translate & { has: (k: string) => boolean };
  const say = (key: string, values?: Record<string, string | number>) => {
    const p = messagePath(key);
    return t.has(p) ? t(p, values) : t('error.generic');
  };
  const loc = (l: Loc) => (locale === 'ar' ? l.ar || l.en : l.en || l.ar);
  const money = (m: Money) => <bdi dir="ltr" className={styles.num}>{`${m.currency} ${m.text}`}</bdi>;
  const when = (iso: string) => {
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? iso : new Intl.DateTimeFormat(locale, { dateStyle: 'long', timeZone: 'UTC' }).format(d);
  };

  const [choice, setChoice] = useState<DecisionKey | null>(initialChoice);
  const [reason, setReason] = useState('');
  const [note, setNote] = useState('');
  const [confirmed, setConfirmed] = useState<ReadonlyArray<string>>([]);
  const [status, setStatus] = useState<Status>({ kind: 'idle' });
  const noteId = useId();
  const opt = view.decisions.find((d) => d.key === choice);
  const ready = !!opt && opt.allowed && reason !== '' && view.confirmations.every((c) => confirmed.includes(c.key)) && status.kind !== 'sending';

  const pickChoice = (d: DecisionKey) => {
    const o = view.decisions.find((x) => x.key === d);
    setChoice(d);
    setReason(o && o.reasons.length === 1 ? o.reasons[0].value : '');
  };
  const send = async () => {
    if (!choice || !ready) return;
    setStatus({ kind: 'sending' });
    const res = await submitDecision(port, view, { decision: choice, reason, note, confirmed });
    setStatus(res.ok ? { kind: 'done' } : { kind: 'error', code: res.code });
  };

  const detail = (d: Detail, key = 'd'): React.ReactNode => (
    <ul className={`${styles.list} ${styles.plain}`} key={key}>
      {Object.entries(d).map(([k, v]) => (
        <li key={k}>
          {t.has(`detail.${k}`) ? <span className={styles.muted}>{t(`detail.${k}`)}: </span> : null}
          {detailValue(v, k)}
        </li>
      ))}
    </ul>
  );
  const detailValue = (v: Detail[string], k: string): React.ReactNode => {
    if (typeof v === 'boolean') return t(v ? 'ui.yes' : 'ui.no');
    if (v === null) return null;
    if (Array.isArray(v)) {
      return v.every((x) => typeof x !== 'object' && x !== null)
        ? <bdi>{new Intl.ListFormat(locale, { style: 'long', type: 'conjunction' }).format(v.map(String))}</bdi>
        : v.map((x, i) => (typeof x === 'object' && x !== null ? detail(x as Detail, `${k}${i}`) : <bdi key={`${k}${i}`}>{String(x)}</bdi>));
    }
    if (typeof v === 'object') return detail(v as Detail, k);
    return <bdi>{String(v)}</bdi>;
  };

  const summary = (s: SummarySection) => (
    <>
      <p className={styles.muted}>{say(s.introKey)}</p>
      <Card className={styles.card}>
        <p className={styles.line}>
          <span className={styles.muted}>{say(s.company.legalNameKey)}</span>
          <bdi className={styles.name}>{loc(s.company.legalName)}</bdi>
        </p>
        {s.company.tradeName ? (
          <p className={styles.line}>
            <span className={styles.muted}>{say(s.company.tradeNameKey)}</span>
            <bdi className={styles.name}>{loc(s.company.tradeName)}</bdi>
          </p>
        ) : null}
      </Card>
      <ul className={`${styles.list} ${styles.plain}`}>
        {s.items.length === 0 ? <li className={styles.muted}>{t('ui.noItems')}</li> : null}
        {s.items.map((it) => (
          <li key={`${it.kind}:${it.id}`}>
            <Card as="article" className={styles.card}>
              <h3>
                <bdi className={styles.name}>{loc(it.labels)}</bdi> <span className={styles.muted}>({say(it.kindKey)})</span>
              </h3>
              {it.details ? detail(it.details) : null}
            </Card>
          </li>
        ))}
      </ul>
      {s.moreItems > 0 ? <Alert tone="warning" title={t('ui.more', { count: s.moreItems })} /> : null}
      <p className={styles.muted}>
        {say(s.notShownNoticeKey)} {s.notShown.map((n) => say(n.labelKey)).join(', ')}.
      </p>
    </>
  );

  const lines = (title: string, rows: ReadonlyArray<QuoteLine>, tot: Totals) => (
    <Card as="article" className={styles.card} aria-label={title}>
      <h3>{title}</h3>
      <ul className={`${styles.list} ${styles.plain}`}>
        {rows.map((r) => (
          <li key={r.id} className={styles.line}>
            <span className={styles.name}>
              {say(r.labelKey, r.params)} <span className={styles.muted}>{t('ui.quantity', { count: r.quantity })}</span>
            </span>
            {money(r.total)}
          </li>
        ))}
        <li className={styles.line}><span>{t('ui.subtotal')}</span>{money(tot.subtotal)}</li>
        <li className={styles.line}><span>{t('ui.vat', { rate: percentText(tot.taxRateBp) })}</span>{money(tot.tax)}</li>
        <li className={`${styles.line} ${styles.total}`}><span>{t('ui.total')}</span>{money(tot.total)}</li>
      </ul>
    </Card>
  );
  const cost = (s: CostSection) => (
    <>
      <Alert tone="warning" title={say(s.noticeKey)}>
        {s.notes.map((n) => (
          <p key={n} className={styles.muted}>{say(n)}</p>
        ))}
      </Alert>
      {lines(t('ui.recurring'), s.lines.recurring, s.totals.recurring)}
      {lines(t('ui.oneOff'), s.lines.one_off, s.totals.one_off)}
      {s.unpriced.length > 0 ? (
        <ul className={styles.list}>
          {s.unpriced.map((u, i) => (
            <li key={i}>{t('ui.unpricedItem', { ref: u.requirement })}</li>
          ))}
        </ul>
      ) : null}
      <p className={styles.muted}>
        {t('ui.validUntil')}: <bdi>{when(s.validUntil)}</bdi>
      </p>
    </>
  );
  const gaps = (s: GapsSection) => (
    <>
      <p>{t('ui.gapCounts', s.counts)}</p>
      {s.noneKey ? <p className={styles.muted}>{say(s.noneKey)}</p> : null}
      <ul className={styles.list}>
        {s.items.map((g, i) => (
          <li key={i}>
            <Badge tone={g.status === 'uncovered' ? 'danger' : 'warning'}>{say(g.statusKey)}</Badge> {say(g.kindKey)}: <bdi>{g.ref}</bdi>
          </li>
        ))}
      </ul>
      {s.moreItems > 0 ? <Alert tone="warning" title={t('ui.more', { count: s.moreItems })} /> : null}
    </>
  );
  const simulation = (s: SimulationSection) => (
    <>
      <p>{say(s.introKey)}</p>
      <ul className={styles.list}>
        {s.checks.map((c) => (
          <li key={c.key}>{say(c.labelKey)}</li>
        ))}
      </ul>
      <p className={styles.muted}>{say(s.noticeKey)}</p>
    </>
  );

  return (
    <section aria-labelledby="oa-title" className={styles.page}>
      <div>
        <h1 id="oa-title">{say(view.titleKey)}</h1>
        <p className={styles.muted}>{say(view.introKey)}</p>
        <p>
          <Badge tone="neutral">{say(view.state.labelKey)}</Badge> <Badge tone="neutral">{say(view.buildStateKey)}</Badge>
        </p>
      </div>
      {view.sections.map((s) => (
        <section key={s.id} aria-labelledby={`oa-${s.id}`} className={styles.section}>
          <h2 id={`oa-${s.id}`}>{say(s.labelKey)}</h2>
          {s.id === 'summary' ? summary(s) : s.id === 'cost' ? cost(s) : s.id === 'gaps' ? gaps(s) : simulation(s)}
        </section>
      ))}
      <section aria-labelledby="oa-decide" className={styles.section}>
        <h2 id="oa-decide">{t('ui.actions')}</h2>
        {view.blockers.length > 0 ? (
          <Alert tone="warning" title={t('ui.blockers')}>
            <ul className={styles.list}>
              {view.blockers.map((b) => (
                <li key={b.key}>{say(b.labelKey)}</li>
              ))}
            </ul>
          </Alert>
        ) : null}
        <p className={styles.muted}>{say(view.stepUpNoticeKey)} {say(view.evidenceNoticeKey)} {say(view.commitNoticeKey)}</p>
        {status.kind === 'done' ? (
          <Alert tone="success" title={t('ui.done')} />
        ) : (
          <>
            <div className={styles.actions} role="group" aria-label={t('ui.actions')}>
              {view.decisions.map((d) => (
                <Button
                  key={d.key}
                  variant={d.key === 'approve' ? 'primary' : d.key === 'reject' ? 'danger' : 'secondary'}
                  disabled={!d.allowed}
                  aria-pressed={choice === d.key}
                  onClick={() => pickChoice(d.key)}
                >
                  {say(d.labelKey)}
                </Button>
              ))}
            </div>
            {opt && opt.allowed ? (
              <div className={styles.form}>
                <Select label={t('ui.reason')} value={reason} onChange={(e) => setReason(e.target.value)}>
                  <option value="">{t('ui.reasonPick')}</option>
                  {opt.reasons.map((r) => (
                    <option key={r.value} value={r.value}>{say(r.labelKey)}</option>
                  ))}
                </Select>
                <TextField
                  id={noteId}
                  label={t('ui.note')}
                  hint={t('ui.noteHint', { limit: view.noteLimit })}
                  maxLength={view.noteLimit}
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                />
                <fieldset>
                  <legend>{t('ui.confirmHeading')}</legend>
                  {view.confirmations.map((c) => (
                    <Checkbox
                      key={c.key}
                      label={say(c.labelKey)}
                      checked={confirmed.includes(c.key)}
                      onChange={(e) => setConfirmed((cur) => (e.target.checked ? [...cur, c.key] : cur.filter((k) => k !== c.key)))}
                    />
                  ))}
                </fieldset>
                {status.kind === 'error' ? <Alert tone="danger" title={t.has(`error.${status.code}`) ? t(`error.${status.code}`) : t('error.generic')} /> : null}
                <Button disabled={!ready} loading={status.kind === 'sending'} onClick={send}>
                  {t('ui.submit', { decision: say(opt.labelKey) })}
                </Button>
              </div>
            ) : null}
          </>
        )}
      </section>
    </section>
  );
}
