'use client';

import { useLocale, useTranslations } from 'next-intl';
import { Alert, Badge, Card, Icon, Mark } from '../../ui';
import { buildBlueprintView } from '../../blueprint/summary';
import { joinList } from '../../blueprint/format';
import { fixtureBlueprint, fixturePending } from '../../blueprint/fixture';
import { fixtureProposal } from '../../blueprint/fixture/proposal';
import { buildProposalView, type ProposalView } from '../../blueprint/proposal';
import type { Badges, BlueprintView as View, Msg, Section } from '../../blueprint/types';
import { callerOf } from '../../lib/session';
import { useSession } from '../shell/SessionProvider';
import { MoneyText } from '../records/Cells';
import { FlowDiagram } from './FlowDiagram';
import { DecisionPanel, GapsSection, ModulesSection, PriceSection, SectionHead, type DecisionPort } from './Proposal';
import { ProgressMarks } from '../marks/ProgressMarks';
import { StatusMark } from '../marks/StatusMark';
import styles from './Blueprint.module.css';

type Translate = (key: string, values?: Record<string, string | number>) => string;

/** Blueprint review (DSC-007, design WEB-029). The caller comes from the session; the data is a fixture until the gateway exists. */
export function BlueprintView() {
  const { session } = useSession();
  const locale = useLocale();
  if (session.status !== 'ready') return null;
  const view = buildBlueprintView(fixtureBlueprint, callerOf(session.claims), locale, fixturePending);
  return <BlueprintDocument view={view} proposal={buildProposalView(fixtureProposal, locale)} locale={locale} />;
}

const num = (i: number) => String(i + 1).padStart(2, '0');

/**
 * Reads like a proposal: a cover (title, status, journey, the key figures), then numbered sections (modules, gaps, the
 * business as drawn, the price) beside a sticky decision card and contents list. Only the owner view (scope "all") gets
 * the modules, gaps, price and decision; a department view is the plain read-only document.
 */
export function BlueprintDocument({ view, proposal, locale, decide }: { view: View; proposal?: ProposalView | null; locale: string; decide?: DecisionPort }) {
  const t = useTranslations('blueprint');
  const tr = t as unknown as Translate;
  const rtl = locale === 'ar';
  const tm = (m: Msg): string =>
    tr(m.key, Object.fromEntries(Object.entries(m.params ?? {}).map(([k, v]) => [k, typeof v === 'object' ? tm(v) : v])));
  const list = (ms: ReadonlyArray<Msg | string>) => joinList(ms.map((m) => (typeof m === 'string' ? m : tm(m))), locale);

  if (view.sections.length === 0) {
    return (
      <section aria-labelledby="bp-title" className={styles.page}>
        <h1 id="bp-title" className={styles.title}>{t('title')}</h1>
        <Alert tone="info" title={t('noAccess.title')}>
          {t('noAccess.body')}
        </Alert>
      </section>
    );
  }

  const p = view.scope === 'all' ? (proposal ?? null) : null;
  const badges = (b: Badges) => (
    <>
      {b.draft ? <StatusMark status="drafted" size={16} /> : null}
      {b.unverified ? <Badge tone="warning" icon={<Icon name="warning" />}>{t('badge.unverified')}</Badge> : null}
    </>
  );
  const val = (f: { value: Msg | string; ltr?: boolean }) => {
    const v = typeof f.value === 'string' ? f.value : tm(f.value);
    return f.ltr ? <bdi dir="ltr">{v}</bdi> : v;
  };
  const facts = (rows: ReadonlyArray<{ label: Msg; value: Msg | string; ltr?: boolean }>) => (
    <Card className={styles.factsCard}>
      <dl className={styles.facts}>
        {rows.map((f, i) => (
          <div key={i} className={styles.factRow}>
            <dt>{tm(f.label)}</dt>
            <dd>{val(f)}</dd>
          </div>
        ))}
      </dl>
    </Card>
  );

  const body = (s: Section) => {
    switch (s.id) {
      case 'profile':
      case 'settings':
        return facts(s.facts);
      case 'places':
        return (
          <div className={styles.grid}>
            {s.locations.length > 0 ? (
              <Card as="article" className={styles.card} aria-label={t('places.locations')}>
                <h3 className={styles.cardTitle}>{t('places.locations')}</h3>
                <ul role="list" className={styles.rows}>
                  {s.locations.map((l) => (
                    <li key={l.id}>
                      <span>{l.label}</span> <span className={styles.muted}>{[tm(l.kind), l.city].filter(Boolean).join(', ')}</span>
                    </li>
                  ))}
                </ul>
              </Card>
            ) : null}
            <Card as="article" className={styles.card} aria-label={t('places.departments')}>
              <h3 className={styles.cardTitle}>{t('places.departments')}</h3>
              <ul role="list" className={styles.rows}>
                {s.departments.map((d) => (
                  <li key={d.id}>{tm(d.label)}</li>
                ))}
              </ul>
            </Card>
          </div>
        );
      case 'roles':
        return (
          <div className={styles.grid}>
            {s.roles.map((r) => (
              <Card as="article" key={r.id} className={styles.card} aria-label={r.label}>
                <div className={styles.cardHead}>
                  <span className={styles.cardIcon} aria-hidden="true"><Icon name="users" /></span>
                  <h3 className={styles.cardTitle}>{r.label}</h3>
                </div>
                <p className={styles.muted}>{tm(r.scope)}</p>
                <ul className={styles.list}>
                  {r.rules.map((p) => (
                    <li key={p.entity}>
                      {t('roles.rule', { entity: p.entity, actions: list(p.actions) })}
                      {p.hidden.length > 0 ? <span className={styles.muted}> {t('roles.hidden', { fields: joinList(p.hidden, locale) })}</span> : null}
                      {p.readOnly.length > 0 ? <span className={styles.muted}> {t('roles.readOnly', { fields: joinList(p.readOnly, locale) })}</span> : null}
                    </li>
                  ))}
                </ul>
              </Card>
            ))}
          </div>
        );
      case 'flows':
        return (
          <>
            {s.flows.map((f) => (
              <Card as="article" key={f.id} className={styles.card} aria-label={f.label}>
                <div className={styles.cardHead}>
                  <span className={styles.cardIcon} aria-hidden="true"><Icon name="workflow" /></span>
                  <h3 className={styles.cardTitle}>{f.label}</h3>
                </div>
                <p className={styles.muted}>{t('flows.entity', { entity: f.entity })}</p>
                <FlowDiagram flow={f} rtl={rtl} label={t('flows.diagram', { name: f.label })} />
                <ol className={styles.steps} aria-label={t('flows.list', { name: f.label })}>
                  {f.steps.map((st) => (
                    <li key={st.n}>
                      <strong className={styles.stepLine}>{t('flows.line', { action: st.action, from: st.from, to: st.to })}</strong>
                      <div className={styles.muted}>{t('flows.by', { who: st.who })}</div>
                      {st.rules.length > 0 ? <div className={styles.muted}>{list(st.rules)}</div> : null}
                      {st.approval ? <div className={styles.muted}>{tm(st.approval)}</div> : null}
                    </li>
                  ))}
                </ol>
                <p className={styles.muted}>{t('flows.legend')}</p>
              </Card>
            ))}
          </>
        );
      case 'items':
        return (
          <div className={styles.grid}>
            {s.entities.map((e) => (
              <Card as="article" key={e.id} className={styles.card} aria-label={e.label}>
                <h3 className={styles.cardTitle}>{e.label}</h3>
                <ul role="list" className={styles.rows}>
                  {e.fields.map((f) => (
                    <li key={f.id}>
                      <span>{f.label}</span> <span className={styles.muted}>{tm(f.type)}{f.required ? `, ${t('items.required')}` : ''}</span>
                    </li>
                  ))}
                </ul>
              </Card>
            ))}
          </div>
        );
      case 'numbering':
        return (
          <Card className={styles.factsCard}>
            <ul role="list" className={styles.rows}>
              {s.rows.map((r) => (
                <li key={r.entity}>
                  <span>{t('numbering.line', { entity: r.entity })}</span>{' '}
                  <span className={styles.rowEnd}>
                    <bdi dir="ltr" className={styles.num}>{r.sample}</bdi> <span className={styles.muted}>{tm(r.reset)}</span>
                  </span>
                </li>
              ))}
            </ul>
          </Card>
        );
      case 'assistants':
        return (
          <div className={styles.grid}>
            {s.assistants.map((a) => (
              <Card as="article" key={a.id} className={styles.card} aria-label={a.label}>
                <div className={styles.cardHead}>
                  <span className={styles.cardIcon} aria-hidden="true"><Mark size={16} /></span>
                  <h3 className={styles.cardTitle}>{a.label}</h3>
                </div>
                <p className={styles.muted}>{tm(a.department)}. {t('assistants.roles', { roles: joinList(a.roles, locale) })}</p>
                <p className={styles.label}>{t('assistants.can')}</p>
                <ul className={styles.list}>
                  {a.tools.map((x, i) => (
                    <li key={i}>
                      {tm(x.text)}
                      {x.confirm ? <span className={styles.muted}> {t('assistants.confirm')}</span> : null}
                    </li>
                  ))}
                </ul>
                <p className={styles.muted}>{tm(a.limits)}</p>
                <p className={styles.muted}>{tm(a.memory)}</p>
              </Card>
            ))}
          </div>
        );
      case 'pending':
        return s.total === 0 ? (
          <p className={styles.lede}>{t('pending.none')}</p>
        ) : (
          <>
            <p className={styles.lede}>{t('pending.total', { count: s.total })}</p>
            <div className={styles.grid}>
              {s.groups.map((g) => (
                <Card as="article" key={g.cls} className={styles.card} aria-label={t(`pending.cls.${g.cls}`)}>
                  <div className={styles.pendingHead}>
                    <h3 className={styles.cardTitle}>{t(`pending.cls.${g.cls}`)}</h3>
                    <Badge tone={g.cls === 'money' || g.cls === 'access' ? 'warning' : 'neutral'}>{g.count}</Badge>
                  </div>
                  <ul className={styles.list}>
                    {g.items.map((m, i) => (
                      <li key={i}>{tm(m)}</li>
                    ))}
                  </ul>
                </Card>
              ))}
            </div>
          </>
        );
    }
  };

  // Section order: modules and gaps first (what is built and what is missing), the business as drawn, the price last.
  const lead = p ? 2 : 0;
  const tocIds = [...(p ? ['modules', 'gaps'] : []), ...view.sections.map((s) => s.id), ...(p ? ['price'] : [])];
  const tocLabel = (id: string) => (id === 'modules' || id === 'gaps' || id === 'price' ? t(`proposal.${id}.title`) : t(`sections.${id}.title`));

  return (
    <div className={styles.page}>
      <header className={styles.cover}>
        <p className={styles.eyebrow}>
          <Mark size={16} />
          <span>{t('proposal.eyebrow')}</span>
          <span className={styles.sep} aria-hidden="true" />
          <span>{t('revision', { n: view.revision })}</span>
        </p>
        <div className={styles.titleRow}>
          <h1 id="bp-title" className={styles.title}>{t('title')}</h1>
          <StatusMark status={view.badges.draft ? 'drafted' : 'approved'} />
          {view.badges.unverified ? <Badge tone="warning">{t('badge.unverified')}</Badge> : null}
        </div>
        <p className={styles.intro}>{t(view.scope === 'all' ? 'intro' : 'introDept')}</p>
        <div className={styles.journey}>
          <ProgressMarks buildState={view.buildState} size={20} />
        </div>
        {p ? (
          <dl className={styles.summary}>
            <div>
              <dt>{t('proposal.summary.modules')}</dt>
              <dd className={styles.kpi}>{p.modules.length}</dd>
            </div>
            <div>
              <dt>{t('proposal.summary.approved')}</dt>
              <dd className={styles.kpi}>{p.approved}</dd>
            </div>
            <div>
              <dt>{t('proposal.summary.gaps')}</dt>
              <dd className={styles.kpi} data-warn={p.gaps.length > 0 ? 'true' : undefined}>{p.gaps.length}</dd>
            </div>
            {p.price ? (
              <div>
                <dt>{t('proposal.summary.monthly')}</dt>
                <dd className={styles.kpi}><MoneyText money={p.price.monthly.total} /></dd>
              </div>
            ) : null}
          </dl>
        ) : null}
      </header>
      {view.scope === 'department' ? (
        <Alert tone="info" title={t('scopeNote.title')}>
          {t('scopeNote.body')}
        </Alert>
      ) : null}
      <div className={styles.layout}>
        <div className={styles.rail}>
          {p ? <DecisionPanel p={p} port={decide} /> : null}
          <nav aria-label={t('toc')} className={styles.toc}>
            <p className={styles.tocTitle}>{t('toc')}</p>
            <ul role="list">
              {tocIds.map((id) => (
                <li key={id}>
                  <a className={styles.tocLink} href={`#bp-${id}`}>
                    {tocLabel(id)}
                  </a>
                </li>
              ))}
            </ul>
          </nav>
        </div>
        <div className={styles.doc}>
          {p ? <ModulesSection p={p} n={num(0)} /> : null}
          {p ? <GapsSection p={p} n={num(1)} /> : null}
          {view.sections.map((s, i) => (
            <section key={s.id} id={`bp-${s.id}`} aria-labelledby={`bp-${s.id}-h`} className={styles.section}>
              <SectionHead
                n={num(lead + i)}
                id={`bp-${s.id}-h`}
                title={t(`sections.${s.id}.title`)}
                hint={t(`sections.${s.id}.hint`)}
                aside={s.id === 'settings' ? <span className={styles.badges}>{badges(s.badges)}</span> : null}
              />
              {body(s)}
            </section>
          ))}
          {p ? <PriceSection p={p} n={num(lead + view.sections.length)} /> : null}
        </div>
      </div>
    </div>
  );
}
