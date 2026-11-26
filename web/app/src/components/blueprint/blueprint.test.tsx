// DSC-007: server-render the viewer in both languages (same approach as shell.test.tsx; no jsdom).
import { describe, expect, it } from 'vitest';
import { renderToString } from 'react-dom/server';
import { NextIntlClientProvider } from 'next-intl';
import type { ReactElement } from 'react';
import { messages } from '../../i18n';
import { buildBlueprintView } from '../../blueprint/summary';
import { fixtureBlueprint, fixturePending } from '../../blueprint/fixture';
import { fixtureProposal } from '../../blueprint/fixture/proposal';
import { buildProposalView } from '../../blueprint/proposal';
import { fixtureSession } from '../../lib/session';
import { Providers } from '../Providers';
import { AppShell } from '../shell/AppShell';
import { SessionProvider } from '../shell/SessionProvider';
import { BlueprintDocument, BlueprintView } from './BlueprintView';

const ENGINE = new RegExp(['fra' + 'ppe', 'ERP' + 'Next'].join('|'), 'i');
const doc = (roles: string[], locale: 'ar' | 'en') =>
  renderToString(
    <div dir={locale === 'ar' ? 'rtl' : 'ltr'}>
      <NextIntlClientProvider locale={locale} messages={messages[locale]}>
        <BlueprintDocument
          view={buildBlueprintView(fixtureBlueprint, { roleIds: roles }, locale, fixturePending)}
          proposal={buildProposalView(fixtureProposal, locale)}
          locale={locale}
        />
      </NextIntlClientProvider>
    </div>,
  );
const shell = (node: ReactElement) =>
  renderToString(
    <Providers>
      <SessionProvider initial={fixtureSession}>
        <AppShell>{node}</AppShell>
      </SessionProvider>
    </Providers>,
  );

describe('blueprint viewer', () => {
  it('renders every section for the owner, with badges, a table of contents and one h1', () => {
    const out = doc(['owner'], 'ar');
    const t = messages.ar.blueprint;
    expect(out.match(/<h1/g)).toHaveLength(1);
    expect(out).not.toContain('<main');
    for (const id of ['profile', 'places', 'roles', 'flows', 'items', 'numbering', 'settings', 'assistants', 'pending']) {
      expect(out).toContain(`id="bp-${id}"`);
      expect(out).toContain(`href="#bp-${id}"`);
    }
    expect(out).toContain(messages.ar.marks.status.drafted);
    expect(out).toContain('data-status="drafted"');
    expect(out).toContain(`aria-label="${messages.ar.marks.progress.title}"`);
    expect(out.match(/aria-current="step"/g)).toHaveLength(1);
    expect(out).toContain(t.badge.unverified);
    expect(out).toContain(t.sections.flows.title);
    expect(out).toContain('<svg');
  });
  it('renders the flow list as the text equivalent of the diagram', () => {
    const out = doc(['owner'], 'en');
    expect(out).toContain('Send for approval: Draft to Pending approval');
    expect(out).toContain('aria-hidden="true"');
  });
  it('mirrors the diagram for right-to-left', () => {
    const x = (html: string) => Number(/<rect x="([\d.]+)"/.exec(html)?.[1]);
    expect(x(doc(['owner'], 'ar'))).toBeGreaterThan(x(doc(['owner'], 'en')));
  });
  it('shows a department view note and no profile to a sales rep', () => {
    const out = doc(['sales_rep'], 'en');
    expect(out).toContain(messages.en.blueprint.scopeNote.title);
    expect(out).not.toContain('id="bp-profile"');
    expect(out).not.toContain('id="bp-pending"');
  });
  it('denies by default', () => {
    const out = doc(['nobody'], 'en');
    expect(out).toContain(messages.en.blueprint.noAccess.title);
    expect(out).not.toContain('id="bp-roles"');
  });
  it('never names the engine in visible text', () => {
    for (const l of ['ar', 'en'] as const) expect(doc(['owner'], l)).not.toMatch(ENGINE);
  });
  it.each(['ar', 'en'] as const)('presents modules with status marks, flagged gaps, a draft price and the two decisions (%s)', (l) => {
    const out = doc(['owner'], l);
    const p = messages[l].blueprint.proposal;
    for (const id of ['modules', 'gaps', 'price', 'decision']) expect(out).toContain(`id="bp-${id}"`);
    for (const m of fixtureProposal.modules) expect(out).toContain(m.labels[l]);
    expect(out).toContain('data-status="approved"');
    for (const g of fixtureProposal.gaps) expect(out).toContain(g.labels[l]);
    expect(out).toContain(p.gaps.status.uncovered);
    expect(out).toContain(p.price.notBinding);
    expect(out).toContain('12,075.00');
    expect(out).toContain(p.decision.approve);
    expect(out).toContain(p.decision.askChanges);
    expect(out).toMatch(/href="\/chat\/?"/);
    expect(out).toContain(p.decision.notLive);
  });
  it('never shows internal ids, component refs or tool names to the owner', () => {
    for (const l of ['ar', 'en'] as const) {
      const text = doc(['owner'], l).replace(/<[^>]+>/g, ' ');
      for (const m of fixtureProposal.modules) expect(text).not.toContain(m.id);
      for (const g of fixtureProposal.gaps) expect(text).not.toContain(g.id);
      expect(text).not.toMatch(/\b[a-z]+_[a-z_]+\b/);
      expect(text).not.toMatch(/\b[a-z_]+\.(list|create|update|delete|transition)\b/);
      expect(text).not.toContain('UNVERIFIED');
    }
  });
  it('gives a sales rep no price and no decision', () => {
    const out = doc(['sales_rep'], 'en');
    expect(out).not.toContain('id="bp-price"');
    expect(out).not.toContain('id="bp-decision"');
  });
  it('sits inside the app shell with one main landmark and a nav item', () => {
    const out = shell(<BlueprintView />);
    expect(out.match(/<main/g)).toHaveLength(1);
    expect(out).toContain('href="/blueprint"'); // a sales rep has a role the Blueprint knows, so the department view is linked
  });
});
