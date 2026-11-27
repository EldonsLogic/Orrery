'use client';

import { useState, type ReactNode } from 'react';
import Link from 'next/link';
import { useTranslations } from 'next-intl';
import { Alert, Badge, Button, Card, Checkbox, Icon } from '../../ui';
import { cx } from '../../ui/cx';
import button from '../../ui/Button.module.css';
import { canApprove, CONFIRMATIONS, type PriceBlockView, type ProposalView } from '../../blueprint/proposal';
import { MoneyText } from '../records/Cells';
import { StatusMark } from '../marks/StatusMark';
import styles from './Blueprint.module.css';

/** The decision port. Not wired until the DSC-009 review is served with a step-up proof (WEB-027, Q-544, Q-683). */
export type DecisionPort = { approve: () => Promise<{ ok: false; reason: 'not_wired' }> };
export const notWiredDecision: DecisionPort = { approve: async () => ({ ok: false, reason: 'not_wired' }) };

/** Modules as cards, each with its status mark: drafted by the AI, or approved by the owner in the chat. */
export function ModulesSection({ p, n }: { p: ProposalView; n: string }) {
  const t = useTranslations('blueprint.proposal.modules');
  return (
    <section id="bp-modules" aria-labelledby="bp-modules-h" className={styles.section}>
      <SectionHead n={n} id="bp-modules-h" title={t('title')} hint={t('hint')} aside={<span className={styles.count}>{t('count', { approved: p.approved, total: p.modules.length })}</span>} />
      <ul role="list" className={styles.modules}>
        {p.modules.map((m) => (
          <li key={m.id} className={styles.module} data-status={m.status}>
            <span className={styles.moduleIcon} aria-hidden="true">
              <Icon name={m.icon} size="md" />
            </span>
            <h3 className={styles.moduleName}>{m.label}</h3>
            <p className={styles.moduleText}>{m.summary}</p>
            <StatusMark status={m.status} size={16} className={styles.moduleStatus} />
          </li>
        ))}
      </ul>
    </section>
  );
}

/** What no module covers: flagged with a word and an icon, and what we will do about each. */
export function GapsSection({ p, n }: { p: ProposalView; n: string }) {
  const t = useTranslations('blueprint.proposal.gaps');
  return (
    <section id="bp-gaps" aria-labelledby="bp-gaps-h" className={styles.section}>
      <SectionHead
        n={n}
        id="bp-gaps-h"
        title={t('title')}
        hint={t('hint')}
        aside={p.gaps.length > 0 ? <Badge tone="warning" icon={<Icon name="warning" />}>{t('count', { count: p.gaps.length })}</Badge> : null}
      />
      {p.gaps.length === 0 ? (
        <p className={styles.lede}>{t('none')}</p>
      ) : (
        <ul role="list" className={styles.gaps}>
          {p.gaps.map((g) => (
            <li key={g.id} className={styles.gap} data-status={g.status}>
              <div className={styles.gapHead}>
                <h3 className={styles.gapName}>{g.label}</h3>
                <Badge tone={g.status === 'uncovered' ? 'warning' : 'neutral'} icon={<Icon name={g.status === 'uncovered' ? 'warning' : 'statusOpen'} />}>
                  {t(`status.${g.status}`)}
                </Badge>
              </div>
              <p className={styles.gapKind}>{t(`kind.${g.kind}`)}</p>
              <p className={styles.gapPlan}>
                <span className={styles.gapPlanLabel}>{t('plan')}</span> {g.plan}
              </p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** The draft price, as the quote gives it: lines, subtotal, VAT and total per block, figures at the logical end. */
export function PriceSection({ p, n }: { p: ProposalView; n: string }) {
  const t = useTranslations('blueprint.proposal.price');
  const block = (key: 'monthly' | 'oneOff', b: PriceBlockView, rate: string) => (
    <Card className={styles.priceCard}>
      <table className={styles.priceTable}>
        <caption className={styles.priceCaption}>{t(key)}</caption>
        <tbody>
          {b.lines.map((l) => (
            <tr key={l.id}>
              <th scope="row">{l.label}</th>
              <td><MoneyText money={l.amount} /></td>
            </tr>
          ))}
          <tr className={styles.priceSub}>
            <th scope="row">{t('subtotal')}</th>
            <td><MoneyText money={b.subtotal} /></td>
          </tr>
          <tr>
            <th scope="row">{t('vat', { rate })}</th>
            <td><MoneyText money={b.vat} /></td>
          </tr>
          <tr className={styles.priceTotal}>
            <th scope="row">{t('total')}</th>
            <td><MoneyText money={b.total} /></td>
          </tr>
        </tbody>
      </table>
    </Card>
  );
  return (
    <section id="bp-price" aria-labelledby="bp-price-h" className={styles.section}>
      <SectionHead n={n} id="bp-price-h" title={t('title')} hint={t('hint')} />
      {p.price ? (
        <>
          <div className={styles.priceGrid}>
            {block('monthly', p.price.monthly, p.price.vatRate)}
            {block('oneOff', p.price.oneOff, p.price.vatRate)}
          </div>
          <p className={styles.note}>
            <Icon name="statusWaiting" />
            {t('notBinding')}
          </p>
        </>
      ) : (
        <Alert tone="info">{t('unavailable')}</Alert>
      )}
    </section>
  );
}

/** Approve (after three confirmations) or ask for changes in the chat. Nothing goes live from here. */
export function DecisionPanel({ p, port = notWiredDecision }: { p: ProposalView; port?: DecisionPort }) {
  const t = useTranslations('blueprint.proposal');
  const [mode, setMode] = useState<'idle' | 'confirm' | 'sending' | 'not_recorded'>('idle');
  const [confirmed, setConfirmed] = useState<ReadonlySet<string>>(new Set());
  const toggle = (c: string, on: boolean) => {
    const next = new Set(confirmed);
    if (on) next.add(c);
    else next.delete(c);
    setConfirmed(next);
  };
  const approve = () => {
    setMode('sending');
    void port.approve().then(() => setMode('not_recorded'));
  };
  return (
    <Card as="section" id="bp-decision" aria-labelledby="bp-decision-h" className={styles.decision}>
      <h2 id="bp-decision-h" className={styles.decisionTitle}>{t('decision.title')}</h2>
      <p className={styles.decisionIntro}>{t('decision.intro')}</p>
      {p.price ? (
        <dl className={styles.decisionFacts}>
          <div>
            <dt>{t('price.monthly')}</dt>
            <dd><MoneyText money={p.price.monthly.total} /></dd>
          </div>
          <div>
            <dt>{t('price.oneOff')}</dt>
            <dd><MoneyText money={p.price.oneOff.total} /></dd>
          </div>
        </dl>
      ) : null}
      {mode === 'idle' ? (
        <div className={styles.decisionActions}>
          <Button size="lg" onClick={() => setMode('confirm')} disabled={!p.price}>
            {t('decision.approve')}
          </Button>
          <Link href="/chat/" className={cx(button.root, button.secondary, button.lg)}>
            <Icon name="chat" />
            {t('decision.askChanges')}
          </Link>
          <p className={styles.caption}>{t('decision.askHint')}</p>
        </div>
      ) : null}
      {mode === 'confirm' || mode === 'sending' ? (
        <div className={styles.confirm}>
        <fieldset className={styles.confirmSet}>
          <legend className={styles.confirmTitle}>{t('decision.confirmTitle')}</legend>
          {CONFIRMATIONS.map((c) => (
            <Checkbox key={c} label={t(`decision.confirm.${c}`)} checked={confirmed.has(c)} onChange={(e) => toggle(c, e.target.checked)} />
          ))}
          <p className={styles.caption}>
            <Icon name="lock" />
            {t('decision.stepUp')}
          </p>
          <div className={styles.decisionActions}>
            <Button size="lg" disabled={!canApprove(confirmed)} loading={mode === 'sending'} onClick={approve}>
              {t('decision.submit')}
            </Button>
            <Button size="lg" variant="ghost" onClick={() => setMode('idle')}>
              {t('decision.cancel')}
            </Button>
          </div>
        </fieldset>
        </div>
      ) : null}
      <div aria-live="polite">
        {mode === 'not_recorded' ? (
          <Alert tone="info" title={t('decision.notRecordedTitle')}>
            {t('decision.notRecordedBody')}
          </Alert>
        ) : null}
      </div>
      <p className={styles.notLive}>
        <Icon name="lock" />
        {t('decision.notLive')}
      </p>
    </Card>
  );
}

export function SectionHead({ n, id, title, hint, aside }: { n: string; id: string; title: string; hint?: string; aside?: ReactNode }) {
  return (
    <div className={styles.sectionHead}>
      <span className={styles.sectionNum} aria-hidden="true">{n}</span>
      <div className={styles.sectionText}>
        <div className={styles.sectionTitleRow}>
          <h2 id={id} className={styles.sectionTitle}>{title}</h2>
          {aside}
        </div>
        {hint ? <p className={styles.sectionHint}>{hint}</p> : null}
      </div>
    </div>
  );
}
