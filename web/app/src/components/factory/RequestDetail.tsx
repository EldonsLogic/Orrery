'use client';

import { useTranslations } from 'next-intl';
import { Alert, Badge, Card } from '../../ui';
import { evidencedTenants, statusTone, type Reviewer } from '../../factory/model';
import type { FactoryReviewPort } from '../../factory/port';
import { asList, detailLines, plainText } from '../../factory/text';
import type { ComponentRequestRecord } from '../../factory/types';
import { ReviewActions } from './ReviewActions';
import { StatusMark, type StatusMarkKind } from '../marks/StatusMark';
import styles from './Factory.module.css';

/** Untrusted text: always a text node inside <bdi> (so reordering characters cannot leak out), never HTML. */
function P({ v, max }: { v: unknown; max?: number }) {
  return (
    <bdi dir="auto" className={styles.plain}>
      {plainText(v, max)}
    </bdi>
  );
}
/** Identifiers and paths are code-like: always left to right. */
function Code({ v }: { v: unknown }) {
  return (
    <bdi dir="ltr" className={styles.code}>
      {plainText(v, 200)}
    </bdi>
  );
}

/** Brand status mark for the request (BRD-014): no draft yet, drafted by the AI and awaiting review, approved by a person. */
const STATUS_MARK: Partial<Record<string, StatusMarkKind>> = {
  requested: 'not_started',
  needs_human_classification: 'not_started',
  drafted: 'drafted',
  in_review: 'drafted',
  approved: 'approved',
};

type Props = { record: ComponentRequestRecord; reviewer: Reviewer; minTenants: number; port: FactoryReviewPort; locale: 'ar' | 'en'; onDone: () => void };

export function RequestDetail({ record: r, reviewer, minTenants, port, locale, onDone }: Props) {
  const t = useTranslations('console.factory');
  const known = (ns: string, key: string | null | undefined) => (key && t.has(`${ns}.${key}`) ? t(`${ns}.${key}`) : null);
  const reasonText = (code: string | null | undefined) => known('reason', code) ?? <Code v={code} />;
  const d = r.draft;
  const cls = r.classification;
  const nTenants = evidencedTenants(r);
  const needWhy = [...asList(r.history)].reverse().find((e) => e.event === 'needs_classification' && typeof e.detail?.why === 'string')?.detail.why;
  const mark = typeof r.status === 'string' && Object.hasOwn(STATUS_MARK, r.status) ? STATUS_MARK[r.status] : undefined;
  const attestedDraft = !!d && !!r.draft_digest && cls?.draft_attested_digest === r.draft_digest;

  return (
    <article className={styles.detail} aria-labelledby={`h-${r.id}`}>
      <header className={styles.block}>
        <h1 id={`h-${r.id}`}>
          <Code v={r.id} />
        </h1>
        <p>
          {mark ? <><StatusMark status={mark} />{' '}</> : null}
          <Badge tone={statusTone(r.status)}>{known('status', r.status) ?? <Code v={r.status} />}</Badge>{' '}
          <Badge tone="neutral">{known('kind', r.need?.kind) ?? <Code v={r.need?.kind} />}</Badge>
        </p>
        <p className={styles.note}>{t('plainTextNote')}</p>
        <dl className={styles.facts}>
          <dt>{t('summary.need')}</dt>
          <dd><Code v={r.need?.ref} /></dd>
          <dt>{t('summary.requestedBy')}</dt>
          <dd><Code v={r.requested_by} /></dd>
          <dt>{t('summary.drafter')}</dt>
          <dd>{r.drafted_by ? <Code v={r.drafted_by} /> : t('none')}</dd>
          <dt>{t('summary.submitter')}</dt>
          <dd>{r.submitted_by ? <Code v={r.submitted_by} /> : t('none')}</dd>
          <dt>{t('summary.createdAt')}</dt>
          <dd><Code v={r.created_at} /></dd>
        </dl>
        {asList(r.flags).length ? (
          <Alert tone="warning" title={t('flags.title')}>
            {asList(r.flags).map((f) => (
              <p key={f}>{reasonText(f)}</p>
            ))}
          </Alert>
        ) : null}
        {r.refusal ? (
          <Alert tone="danger" title={t('refusal.title')}>
            <p>{reasonText(r.refusal.code)}</p>
            <p>{t('refusal.route')}</p>
          </Alert>
        ) : null}
        {r.decision ? (
          <Alert tone={r.decision.outcome === 'approved' ? 'success' : 'danger'} title={t('decision.title')}>
            <p>
              {known('decisionOutcome', r.decision.outcome) ?? <Code v={r.decision.outcome} />} {t('decision.by')} <Code v={r.decision.by} /> <Code v={r.decision.at} />
            </p>
            {r.decision.reason ? <p>{known('rejectReason', r.decision.reason) ?? <Code v={r.decision.reason} />}</p> : null}
          </Alert>
        ) : null}
      </header>

      <ReviewActions key={r.id} record={r} reviewer={reviewer} minTenants={minTenants} port={port} onDone={onDone} />

      <Card as="section" className={styles.block} aria-labelledby={`risk-${r.id}`}>
        <h2 id={`risk-${r.id}`}>{t('risk.title')}</h2>
        <p className={styles.note}>{t('risk.note')}</p>
        {typeof needWhy === 'string' ? (
          <p>
            {t('risk.needStage')}: {known('why', needWhy) ?? <Code v={needWhy} />}
          </p>
        ) : null}
        {cls?.need_attested_by ? (
          <p>
            {t('risk.needAttested')} <Code v={cls.need_attested_by} />
          </p>
        ) : null}
        {cls?.draft ? (
          <>
            <p>
              <Badge tone={cls.draft.proven ? 'success' : 'warning'}>{cls.draft.proven ? t('risk.proven') : t('risk.unproven')}</Badge>{' '}
              {cls.draft.has_money_field ? <Badge tone="danger">{t('risk.money')}</Badge> : null}
            </p>
            {asList(cls.draft.reasons).length ? (
              <>
                <h3>{t('risk.reasons')}</h3>
                <ul>
                  {asList(cls.draft.reasons).map((w) => (
                    <li key={w}>{known('why', w) ?? <Code v={w} />}</li>
                  ))}
                </ul>
              </>
            ) : null}
            {!cls.draft.proven ? (
              <p>
                {attestedDraft ? (
                  <>
                    {t('risk.draftAttested')} <Code v={cls.draft_attested_by} />
                  </>
                ) : (
                  t('risk.draftNotAttested')
                )}
              </p>
            ) : null}
          </>
        ) : (
          <p>{t('risk.noDraft')}</p>
        )}
      </Card>

      <Card as="section" className={styles.block} aria-labelledby={`draft-${r.id}`}>
        <h2 id={`draft-${r.id}`}>{t('draft.title')}</h2>
        {!d ? (
          <p>{t('draft.none')}</p>
        ) : (
          <>
            <dl className={styles.facts}>
              <dt>{t('draft.id')}</dt>
              <dd><Code v={d.manifest?.id} /></dd>
              <dt>{t('draft.version')}</dt>
              <dd><Code v={d.manifest?.version} /></dd>
              <dt>{t('draft.name')}</dt>
              <dd><P v={d.manifest?.name?.[locale]} max={200} /></dd>
              <dt>{t('draft.description')}</dt>
              <dd><P v={d.manifest?.description} /></dd>
            </dl>
            <h3>{t('draft.provides')}</h3>
            <ul>
              {asList(d.manifest?.provides).flatMap((p, i) =>
                asList(p?.artifacts).map((a, j) => (
                  <li key={`${i}-${j}`}>
                    <Code v={p?.capability} /> <Code v={a?.type} /> <Code v={a?.ref} />
                  </li>
                )),
              )}
            </ul>
            <h3>{t('draft.capabilities')}</h3>
            <ul>
              {asList(d.spec?.capabilities).map((c, i) => (
                <li key={i}>
                  <Code v={c?.id} />: <P v={c?.summary} max={400} />
                </li>
              ))}
            </ul>
            <h3>{t('draft.fields')}</h3>
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <caption className={styles.srOnly}>{t('draft.fields')}</caption>
                <thead>
                  <tr>
                    <th scope="col">{t('draft.col.entity')}</th>
                    <th scope="col">{t('draft.col.field')}</th>
                    <th scope="col">{t('draft.col.type')}</th>
                    <th scope="col">{t('draft.col.required')}</th>
                    <th scope="col">{t('draft.col.options')}</th>
                  </tr>
                </thead>
                <tbody>
                  {asList(d.spec?.fields).map((f, i) => (
                    <tr key={i}>
                      <td><Code v={f?.entity} /></td>
                      <th scope="row"><Code v={f?.name} /></th>
                      <td><Code v={f?.type} /></td>
                      <td>{f?.required ? t('yes') : t('no')}</td>
                      <td><P v={asList(f?.options).join(', ') || f?.target} max={300} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <h3>{t('draft.permissions')}</h3>
            <ul>
              {asList(d.spec?.permissions).map((p, i) => (
                <li key={i}>
                  <Code v={p?.role} /> <Code v={p?.action} />
                </li>
              ))}
            </ul>
            <h3>{t('draft.i18nKeys')}</h3>
            <p>{asList(d.spec?.i18n_keys).map((k, i) => <span key={i}><Code v={k} />{' '}</span>)}</p>
          </>
        )}
      </Card>

      <Card as="section" className={styles.block} aria-labelledby={`tests-${r.id}`}>
        <h2 id={`tests-${r.id}`}>{t('tests.title')}</h2>
        {!d ? (
          <p>{t('draft.none')}</p>
        ) : (
          <>
            <h3>{t('tests.plan')}</h3>
            <ul>
              {asList(d.spec?.test_plan).map((p, i) => (
                <li key={i}>
                  <Code v={p?.id} /> <Code v={p?.kind} /> {t('tests.covers')}{' '}
                  <Code v={Array.isArray(p?.covers) ? p.covers.join(', ') : p?.covers} /> {p?.blocking ? <Badge tone="danger">{t('tests.blocking')}</Badge> : null}
                </li>
              ))}
            </ul>
            <h3>{t('tests.files')}</h3>
            <ul>
              {asList(d.manifest?.tests).map((x, i) => (
                <li key={i}>
                  <Code v={x?.id} /> <Code v={x?.kind} /> <Code v={x?.path} /> {x?.blocking ? <Badge tone="danger">{t('tests.blocking')}</Badge> : null}
                </li>
              ))}
            </ul>
          </>
        )}
      </Card>

      <Card as="section" className={styles.block} aria-labelledby={`gen-${r.id}`}>
        <h2 id={`gen-${r.id}`}>{t('gen.title')}</h2>
        <p>
          <Badge tone={nTenants >= minTenants || r.generalisation?.attested_by ? 'success' : 'warning'}>
            {nTenants >= minTenants || r.generalisation?.attested_by ? t('gen.met') : t('gen.notMet')}
          </Badge>{' '}
          {t('gen.count', { n: nTenants, min: minTenants })}
        </p>
        <p>
          {r.generalisation?.attested_by ? (
            <>
              {t('gen.attested')} <Code v={r.generalisation.attested_by} /> <Code v={r.generalisation.attested_at} />
            </>
          ) : (
            t('gen.notAttested')
          )}
        </p>
        {d?.generalisation ? (
          <>
            <h3>{t('gen.rationale')}</h3>
            <p className={styles.note}>{t('gen.rationaleNote')}</p>
            <p><P v={d.generalisation.rationale} /></p>
            {d.generalisation.tenant_specific ? <Badge tone="danger">{t('gen.tenantSpecific')}</Badge> : null}
          </>
        ) : null}
      </Card>

      <Card as="section" className={styles.block} aria-labelledby={`ev-${r.id}`}>
        <h2 id={`ev-${r.id}`}>{t('evidence.title')}</h2>
        <p className={styles.note}>{t('evidence.note')}</p>
        {Object.keys(r.tenants ?? {}).length === 0 ? (
          <p>{t('evidence.none')}</p>
        ) : (
          Object.entries(r.tenants).map(([ref, items]) => (
            <div key={ref} className={styles.tenant}>
              <h3>
                {t('evidence.tenant')} <Code v={ref} />
              </h3>
              <ul>
                {asList(items).map((e, i) => (
                  <li key={i}>
                    <Code v={e?.kind} /> <Code v={e?.id} />
                  </li>
                ))}
              </ul>
            </div>
          ))
        )}
      </Card>

      <Card as="section" className={styles.block} aria-labelledby={`hist-${r.id}`}>
        <h2 id={`hist-${r.id}`}>{t('history.title')}</h2>
        <ol className={styles.history}>
          {asList(r.history).map((e) => (
            <li key={e.seq}>
              <Code v={e.at} /> <Badge tone="neutral">{known('actorKind', e.actor_kind) ?? <Code v={e.actor_kind} />}</Badge> <Code v={e.actor} />{' '}
              <strong>{known('event', e.event) ?? <Code v={e.event} />}</strong>
              {e.from ? (
                <>
                  {' '}
                  <Code v={e.from} /> {'→'} <Code v={e.to} />
                </>
              ) : null}
              {e.code ? <> {reasonText(e.code)}</> : null}
              {detailLines(e.detail).map((l, i) => (
                <div key={i} className={styles.detailLine}>
                  <P v={l} max={260} />
                </div>
              ))}
            </li>
          ))}
        </ol>
      </Card>
    </article>
  );
}
