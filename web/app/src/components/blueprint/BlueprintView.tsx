'use client';

import { useLocale, useTranslations } from 'next-intl';
import { Alert, Badge, Card } from '../../ui';
import { buildBlueprintView } from '../../blueprint/summary';
import { joinList } from '../../blueprint/format';
import { fixtureBlueprint, fixturePending } from '../../blueprint/fixture';
import type { Badges, BlueprintView as View, Msg, Section } from '../../blueprint/types';
import { callerOf } from '../../lib/session';
import { useSession } from '../shell/SessionProvider';
import { FlowDiagram } from './FlowDiagram';
import { ProgressMarks } from '../marks/ProgressMarks';
import { StatusMark } from '../marks/StatusMark';
import styles from './Blueprint.module.css';

type Translate = (key: string, values?: Record<string, string | number>) => string;

/** Read-only Blueprint viewer (DSC-007). The caller comes from the session; the data is a fixture until the gateway exists. */
export function BlueprintView() {
  const { session } = useSession();
  const locale = useLocale();
  if (session.status !== 'ready') return null;
  const view = buildBlueprintView(fixtureBlueprint, callerOf(session.claims), locale, fixturePending);
  return <BlueprintDocument view={view} locale={locale} />;
}

export function BlueprintDocument({ view, locale }: { view: View; locale: string }) {
  const t = useTranslations('blueprint');
  const tr = t as unknown as Translate;
  const rtl = locale === 'ar';
  const tm = (m: Msg): string =>
    tr(m.key, Object.fromEntries(Object.entries(m.params ?? {}).map(([k, v]) => [k, typeof v === 'object' ? tm(v) : v])));
  const list = (ms: ReadonlyArray<Msg | string>) => joinList(ms.map((m) => (typeof m === 'string' ? m : tm(m))), locale);

  if (view.sections.length === 0) {
    return (
      <section aria-labelledby="bp-title" className={styles.page}>
        <h1 id="bp-title">{t('title')}</h1>
        <Alert tone="info" title={t('noAccess.title')}>
          {t('noAccess.body')}
        </Alert>
      </section>
    );
  }

  const badges = (b: Badges) => (
    <>
      {b.draft ? <StatusMark status="drafted" /> : null}
      {b.unverified ? <Badge tone="warning">{t('badge.unverified')}</Badge> : null}
    </>
  );
  const facts = (rows: ReadonlyArray<{ label: Msg; value: Msg | string; ltr?: boolean }>) => (
    <dl className={styles.facts}>
      {rows.map((f, i) => (
        <div key={i} className={styles.factRow}>
          <dt>{tm(f.label)}</dt>
          <dd>{f.ltr ? <bdi dir="ltr">{typeof f.value === 'string' ? f.value : tm(f.value)}</bdi> : typeof f.value === 'string' ? f.value : tm(f.value)}</dd>
        </div>
      ))}
    </dl>
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
                <h3>{t('places.locations')}</h3>
                <ul className={`${styles.list} ${styles.plain}`}>
                  {s.locations.map((l) => (
                    <li key={l.id}>
                      {l.label} <span className={styles.muted}>({[tm(l.kind), l.city].filter(Boolean).join(', ')})</span>
                    </li>
                  ))}
                </ul>
              </Card>
            ) : null}
            <Card as="article" className={styles.card} aria-label={t('places.departments')}>
              <h3>{t('places.departments')}</h3>
              <ul className={`${styles.list} ${styles.plain}`}>
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
                <h3>{r.label}</h3>
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
                <h3>{f.label}</h3>
                <p className={styles.muted}>{t('flows.entity', { entity: f.entity })}</p>
                <FlowDiagram flow={f} rtl={rtl} label={t('flows.diagram', { name: f.label })} />
                <ol className={styles.steps} aria-label={t('flows.list', { name: f.label })}>
                  {f.steps.map((st) => (
                    <li key={st.n}>
                      <strong>{t('flows.line', { action: st.action, from: st.from, to: st.to })}</strong>
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
                <h3>{e.label}</h3>
                <ul className={`${styles.list} ${styles.plain}`}>
                  {e.fields.map((f) => (
                    <li key={f.id}>
                      {f.label} <span className={styles.muted}>({tm(f.type)}{f.required ? `, ${t('items.required')}` : ''})</span>
                    </li>
                  ))}
                </ul>
              </Card>
            ))}
          </div>
        );
      case 'numbering':
        return (
          <ul className={`${styles.list} ${styles.plain}`}>
            {s.rows.map((r) => (
              <li key={r.entity}>
                {t('numbering.line', { entity: r.entity })} <bdi dir="ltr" className={styles.num}>{r.sample}</bdi> <span className={styles.muted}>{tm(r.reset)}</span>
              </li>
            ))}
          </ul>
        );
      case 'assistants':
        return (
          <div className={styles.grid}>
            {s.assistants.map((a) => (
              <Card as="article" key={a.id} className={styles.card} aria-label={a.label}>
                <h3>{a.label}</h3>
                <p className={styles.muted}>{tm(a.department)}. {t('assistants.roles', { roles: joinList(a.roles, locale) })}</p>
                <p className={styles.muted}>{t('assistants.can')}</p>
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
          <p>{t('pending.none')}</p>
        ) : (
          <>
            <p>{t('pending.total', { count: s.total })}</p>
            <div className={styles.grid}>
              {s.groups.map((g) => (
                <Card as="article" key={g.cls} className={styles.card} aria-label={t(`pending.cls.${g.cls}`)}>
                  <div className={styles.pendingHead}>
                    <h3>{t(`pending.cls.${g.cls}`)}</h3>
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

  return (
    <div className={styles.page}>
      <header className={styles.head}>
        <h1 id="bp-title">{t('title')}</h1>
        <StatusMark status={view.badges.draft ? 'drafted' : 'approved'} />
        {view.badges.unverified ? <Badge tone="warning">{t('badge.unverified')}</Badge> : null}
        <p className={styles.muted}>{t('revision', { n: view.revision })}</p>
        <ProgressMarks buildState={view.buildState} />
      </header>
      <p>{t(view.scope === 'all' ? 'intro' : 'introDept')}</p>
      {view.scope === 'department' ? (
        <Alert tone="info" title={t('scopeNote.title')}>
          {t('scopeNote.body')}
        </Alert>
      ) : null}
      <nav aria-label={t('toc')} className={styles.toc}>
        <ul>
          {view.sections.map((s) => (
            <li key={s.id}>
              <a className={styles.link} href={`#bp-${s.id}`}>
                {t(`sections.${s.id}.title`)}
              </a>
            </li>
          ))}
        </ul>
      </nav>
      {view.sections.map((s) => (
        <section key={s.id} id={`bp-${s.id}`} aria-labelledby={`bp-${s.id}-h`} className={styles.section}>
          <div className={styles.sectionHead}>
            <h2 id={`bp-${s.id}-h`}>{t(`sections.${s.id}.title`)}</h2>
            {s.id === 'settings' ? badges(s.badges) : null}
          </div>
          <p className={styles.muted}>{t(`sections.${s.id}.hint`)}</p>
          {body(s)}
        </section>
      ))}
    </div>
  );
}
