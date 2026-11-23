'use client';

import { useId, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { Alert, Badge, Button, Card, Checkbox, Select, TextField } from '../../ui';
import { joinList, regionName } from '../../blueprint/format';
import { messagePath, percentText } from '../../approval/labels';
import { buildRequest, emptyForm, formKey, nextStatus, submitDecision, type Form, type Status } from '../../approval/decide';
import type {
  ApprovalPort, CostSection, Detail, DecisionKey, GapsSection, Loc, Money, QuoteLine, ReviewModel, SimulationSection, SummarySection, Totals,
} from '../../approval/types';
import styles from './Approval.module.css';

type Translate = (key: string, values?: Record<string, string | number>) => string;
const isolate = (v: string): string => `\u2068${v}\u2069`; // keep untrusted text from reordering what is around it

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
    return t.has(p) ? t(p, values) : t('ui.unknownLabel');
  };
  const loc = (l: Loc) => (locale === 'ar' ? l.ar || l.en : l.en || l.ar) + (l.cut ? ` ${t('ui.cut')}` : '');
  const list = (items: ReadonlyArray<string>) => joinList(items, locale);
  const money = (m: Money) => <bdi dir="ltr" className={styles.num}>{`${m.currency} ${m.text}`}</bdi>;
  const when = (iso: string) => {
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? iso : new Intl.DateTimeFormat(locale, { dateStyle: 'long', timeZone: 'UTC' }).format(d);
  };

  // The form belongs to the view it was filled against: when either digest changes, the choice, reason, note and ticks are gone.
  const [stored, setStored] = useState<Form | null>(initialChoice ? emptyForm(view, initialChoice) : null);
  const [status, setStatus] = useState<Status>({ kind: 'idle' });
  const form = stored && stored.for === formKey(view) ? stored : null;
  const noteId = useId();
  const choice = form?.decision ?? null;
  const opt = view.decisions.find((d) => d.key === choice);
  const stale = status.kind === 'stale';
  const ready = !!form && buildRequest(view, form) !== null && status.kind !== 'sending' && !stale;
  const patch = (p: Partial<Form>) => form && setStored({ ...form, ...p });

  const pickChoice = (d: DecisionKey) => setStored(emptyForm(view, d));
  const send = async () => {
    if (!form || !ready) return;
    setStatus({ kind: 'sending' });
    setStatus(nextStatus(await submitDecision(port, view, form)));
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
      <Card className={styles.card}>
        {/^[A-Z]{2}$/.test(s.compliance.country) ? (
          <p className={styles.line}>
            <span className={styles.muted}>{t('ui.country')}</span>
            <bdi>{regionName(s.compliance.country, locale)}</bdi>
          </p>
        ) : null}
        {s.compliance.vatRegistered === null ? null : (
          <p className={styles.line}>
            <span className={styles.muted}>{t('ui.vatRegistered')}</span>
            <span>{t(s.compliance.vatRegistered ? 'ui.yes' : 'ui.no')}</span>
          </p>
        )}
        {s.compliance.eInvoicingMode ? (
          <p className={styles.line}>
            <span className={styles.muted}>{t('ui.eInvoicing')}</span>
            <bdi>{t.has(`ui.mode.${s.compliance.eInvoicingMode}`) ? t(`ui.mode.${s.compliance.eInvoicingMode}`) : t('ui.unknownLabel')}</bdi>
          </p>
        ) : null}
      </Card>
      <p className={styles.muted}>
        {t('ui.counts')}: {list(Object.entries(s.counts).filter(([, n]) => n > 0).map(([k, n]) => `${say(`oa.kind.${k}`)} ${n}`))}
      </p>
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
        {say(s.notShownNoticeKey)} {list(s.notShown.map((n) => say(n.labelKey)))}.
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
              {say(r.labelKey, Object.fromEntries(Object.entries(r.params).map(([k, v]) => [k, isolate(v)])))} <span className={styles.muted}>{t('ui.quantity', { count: r.quantity })}</span>
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
            <li key={i}>{t('ui.unpricedItem', { ref: isolate(u.requirement) })}</li>
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
        {stale ? <Alert tone="danger" title={t('error.OA-006')} /> : null}
        {status.kind === 'error' ? <Alert tone="danger" title={t.has(`error.${status.code}`) ? t(`error.${status.code}`) : t('error.generic')} /> : null}
        {status.kind === 'done' ? (
          <Alert tone="success" title={t('ui.done')} />
        ) : (
          <>
            <div className={styles.actions} role="group" aria-label={t('ui.actions')}>
              {view.decisions.map((d) => (
                <Button
                  key={d.key}
                  variant={d.key === 'approve' ? 'primary' : d.key === 'reject' ? 'danger' : 'secondary'}
                  disabled={!d.allowed || stale}
                  aria-pressed={choice === d.key}
                  onClick={() => pickChoice(d.key)}
                >
                  {say(d.labelKey)}
                </Button>
              ))}
            </div>
            {opt && opt.allowed && !stale ? (
              <div className={styles.form}>
                <Select label={t('ui.reason')} value={form?.reason ?? ''} onChange={(e) => patch({ reason: e.target.value })}>
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
                  value={form?.note ?? ''}
                  onChange={(e) => patch({ note: e.target.value })}
                />
                {opt.key === 'approve' ? (
                  <fieldset>
                    <legend>{t('ui.confirmHeading')}</legend>
                    {view.confirmations.map((c) => (
                      <Checkbox
                        key={c.key}
                        label={say(c.labelKey)}
                        checked={form?.confirmed.includes(c.key) ?? false}
                        onChange={(e) => patch({ confirmed: e.target.checked ? [...(form?.confirmed ?? []), c.key] : (form?.confirmed ?? []).filter((k) => k !== c.key) })}
                      />
                    ))}
                  </fieldset>
                ) : null}
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
