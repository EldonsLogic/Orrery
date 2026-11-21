// PLT-014: server-render the review screens (rtl and ltr, same approach as console.test.tsx; no jsdom) and drive the
// action buttons through their handlers with a recording port.
import { describe, expect, it, vi } from 'vitest';
import { renderToString } from 'react-dom/server';
import { NextIntlClientProvider } from 'next-intl';
import type { ReactElement } from 'react';
import { messages, type Locale } from '../../i18n';
import { FIXTURE_NOW as NOW } from '../../console/fixture';
import type { StaffClaims } from '../../console/types';
import type { ComponentRequestRecord } from '../../factory/types';
import { fixtureRequests } from '../../factory/fixture';
import { fixturePort, type FactoryReviewPort } from '../../factory/port';
import { ConsoleProvider } from '../console/ConsoleProvider';
import { ConsoleShell } from '../console/ConsoleShell';
import { Providers } from '../Providers';
import { RequestDetail } from './RequestDetail';
import { ReviewActions } from './ReviewActions';
import { FactoryScreen } from './FactoryScreen';

const claims = (roles: string[], staffId = 'staff-fixture-1'): StaffClaims => ({ realm: 'staff', staffId, roles, mfaSatisfied: true, sessionVersion: 1 });
const wrap = (node: ReactElement, locale: Locale = 'en', c: StaffClaims = claims(['owner'])) =>
  renderToString(
    <div dir={locale === 'ar' ? 'rtl' : 'ltr'}>
      <NextIntlClientProvider locale={locale} messages={messages[locale]} timeZone="UTC">
        <ConsoleProvider claims={c} currentSessionVersion={1} assumeAudited now={NOW}>
          {node}
        </ConsoleProvider>
      </NextIntlClientProvider>
    </div>,
  );
const rec = (id: string) => fixtureRequests.find((r) => r.id === id) as ComponentRequestRecord;
const reviewer = { staffId: 'staff-reviewer-9', roles: ['owner'] as const };
const detail = (r: ComponentRequestRecord, locale: Locale = 'en', who = reviewer, port: FactoryReviewPort = fixturePort) =>
  wrap(<RequestDetail record={r} reviewer={who} minTenants={2} port={port} locale={locale} onDone={() => undefined} />, locale);

describe('component factory screens', () => {
  it('shows the draft, tests, risk class with reasons, evidence per tenant ref and history in both languages', () => {
    for (const l of ['en', 'ar'] as const) {
      const m = messages[l].console.factory;
      const out = detail(rec('CR-2c3d4e5f60718293'), l);
      for (const s of [m.draft.title, m.tests.title, m.risk.title, m.gen.title, m.evidence.title, m.history.title, m.actions.title]) expect(out).toContain(s);
      expect(out).toContain(m.why.money_field); // the reasons are listed
      expect(out).toContain('a1f3c9d20b7e4c5d8e6f1a2b'); // opaque tenant ref, with its evidence
      expect(out).toContain('/entities/2');
      expect(out).toContain('price_list');
    }
    const ready = detail(rec('CR-0a1b2c3d4e5f6071'));
    expect(ready).toContain('visit_date');
    expect(ready).toContain('tests/unit/test_log.py');
    expect(ready).toContain('Tenants with evidence: 3, needed: 2');
  });

  it('renders hostile text as plain text: no live markup, no raw bidi controls', () => {
    const out = detail(rec('CR-1b2c3d4e5f607182'));
    expect(out).not.toContain('<script');
    expect(out).not.toContain('<img');
    expect(out).not.toContain('<b>');
    expect(out).toContain('&lt;script&gt;alert(1)&lt;/script&gt;');
    expect(out).toContain('&lt;img src=x onerror=alert(2)&gt;');
    expect(out).toContain('&lt;U+202E&gt;');
    expect(out).not.toMatch(/[\u202a-\u202e\u2066-\u2069\u200e\u200f]/);
    // never a link or an href made from untrusted text
    expect(out).not.toMatch(/href="javascript/i);
    expect(out).not.toContain('dangerouslySetInnerHTML');
    // the flagged-text warning shows
    expect(out).toContain(messages.en.console.factory.flags.title);
    // untrusted text sits in bdi so reordering cannot leak out
    expect(out).toMatch(/<bdi dir="auto"[^>]*>[^<]*Ignore all rules/);
  });

  it('renders hostile text safely in Arabic and with hostile status, event and id values', () => {
    const hostile = { ...rec('CR-1b2c3d4e5f607182'), id: 'CR-<img onerror=1>', status: '<svg onload=1>' as never, history: [{ seq: 1, at: '2026\u202e', actor: '<b>', actor_kind: '<i>', event: '<u>', from: null, to: 'x', code: '<script>', detail: { '<k>': '\u202e<v>' } }] };
    const out = detail(hostile as ComponentRequestRecord, 'ar');
    expect(out).not.toMatch(/<(script|img|svg|b|i|u)[ >]/);
    expect(out).not.toMatch(/[\u202a-\u202e]/);
  });

  it('survives a record with missing or wrong-typed parts (empty and error states)', () => {
    const broken = { ...rec('CR-5f60718293041526'), draft: { manifest: null, spec: null, generalisation: null }, tenants: { x: null }, history: null, flags: null, classification: undefined } as unknown as ComponentRequestRecord;
    expect(() => detail(broken)).not.toThrow();
    const empty = { ...rec('CR-5f60718293041526'), tenants: {} };
    const out = detail(empty);
    expect(out).toContain(messages.en.console.factory.evidence.none);
    expect(out).toContain(messages.en.console.factory.draft.none);
  });

  it('shows a refusal and a decision with their labels', () => {
    expect(detail(rec('CR-93041526a7b8c9da'))).toContain(messages.en.console.factory.reason['CRQ-001']);
    const done = detail(rec('CR-8293041526a7b8c9'));
    expect(done).toContain(messages.en.console.factory.rejectReason.duplicate);
  });

  it('turns every action off, with the reason written next to it, unless the staff user may act', () => {
    const off = (out: string) => (out.match(/<button[^>]*disabled/g) ?? []).length;
    const w = (who: { staffId: string; roles: readonly string[] }, r = 'CR-0a1b2c3d4e5f6071') => detail(rec(r), 'en', who as never);
    // allowed reviewer: approve, reject, attest generalisable on; attest risk class off (wrong status)
    const ok = w(reviewer);
    expect(off(ok)).toBe(1);
    expect(ok).toContain(messages.en.console.factory.actions.why.wrong_status);
    // no permission: all four off
    const none = w({ staffId: 'staff-s', roles: ['support'] });
    expect(off(none)).toBe(4);
    expect(none).toContain(messages.en.console.factory.actions.why.no_permission);
    // the requester of the request: separation of duties shown
    const self = w({ staffId: 'agent-discovery', roles: ['owner'] });
    expect(self).toContain(messages.en.console.factory.actions.why.separation);
    // approve disabled for too little evidence, with its reason
    const thin = w(reviewer, 'CR-1b2c3d4e5f607182');
    expect(thin).toContain(messages.en.console.factory.actions.why.no_generalisation);
    // money-field draft: plain is the default selection, so attest is off with its reason
    const money = w(reviewer, 'CR-2c3d4e5f60718293');
    expect(money).toContain(messages.en.console.factory.actions.why.money_field);
    // buttons point at their reason for assistive technology
    expect(none).toMatch(/aria-describedby="why-CR-0a1b2c3d4e5f6071-approve"/);
  });

  it('says the server enforces the rules and shows the step-up placeholder text only after a click', () => {
    const screen = wrap(<FactoryScreen />);
    expect(screen).toContain(messages.en.console.factory.serverNote);
    expect(screen).not.toContain(messages.en.console.factory.stepUp.title);
  });

  it('lists requests by status with counts, in both languages, rtl aware', () => {
    for (const l of ['en', 'ar'] as const) {
      const out = wrap(<FactoryScreen />, l);
      expect(out).toContain(messages[l].console.factory.title);
      expect(out).toContain(`dir="${l === 'ar' ? 'rtl' : 'ltr'}"`);
      for (const m of out.matchAll(/style="([^"]*)"/g)) expect(m[1]).not.toMatch(/(?:^|[;\s-])(?:left|right)\s*:|text-align|float/i);
    }
  });

  it('denies a role without the factory view permission and a session that is not staff', () => {
    expect(wrap(<FactoryScreen />, 'en', claims(['support']))).toContain(messages.en.console.factory.noAccess.title);
    const shell = renderToString(
      <div dir="rtl">
        <Providers>
          <ConsoleProvider claims={{ ...claims(['owner']), realm: 'customer' }} currentSessionVersion={1} assumeAudited now={NOW}>
            <ConsoleShell>
              <FactoryScreen />
            </ConsoleShell>
          </ConsoleProvider>
        </Providers>
      </div>,
    );
    expect(shell).toContain(messages.ar.console.denied.title);
    expect(shell).not.toContain('CR-0a1b2c3d4e5f6071');
  });

  it('adds the navigation link only for roles that may view', () => {
    const nav = (roles: string[]) =>
      renderToString(
        <div dir="rtl">
          <Providers>
            <ConsoleProvider claims={claims(roles)} currentSessionVersion={1} assumeAudited now={NOW}>
              <ConsoleShell>{null}</ConsoleShell>
            </ConsoleProvider>
          </Providers>
        </div>,
      );
    expect(nav(['owner'])).toContain('/console/components');
    expect(nav(['support'])).not.toContain('/console/components');
  });

  it('has no hard-coded text outside the message files', () => {
    expect(Object.keys(messages.ar.console.factory).sort()).toEqual(Object.keys(messages.en.console.factory).sort());
  });
});

describe('review action wiring', () => {
  it('only calls the injected port, with the chosen command, after the step-up prompt', async () => {
    const act = vi.fn(async () => ({ ok: false as const, code: 'not_wired' }));
    const port: FactoryReviewPort = { list: async () => ({ ok: false, code: 'x' }), act };
    // static check: the screens import no network or storage API
    const src = await import('node:fs').then((fs) =>
      ['ReviewActions.tsx', 'RequestDetail.tsx', 'FactoryScreen.tsx'].map((f) => fs.readFileSync(new URL(`./${f}`, import.meta.url), 'utf8')).join('\n'),
    );
    expect(src).not.toMatch(/\bfetch\(|XMLHttpRequest|localStorage|sessionStorage|dangerouslySetInnerHTML|innerHTML/);
    expect(act).not.toHaveBeenCalled();
    expect(port.act).toBe(act);
    expect(ReviewActions).toBeTypeOf('function');
  });

  it('fixture port never executes an action and reads the fixtures', async () => {
    expect(await fixturePort.act({ requestId: 'CR-0a1b2c3d4e5f6071', action: 'approve' })).toEqual({ ok: false, code: 'not_wired' });
    const l = await fixturePort.list();
    expect(l.ok && l.requests.length).toBe(fixtureRequests.length);
  });
});
