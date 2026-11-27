// PLT-012: server-render the console in rtl and ltr (same approach as shell.test.tsx; no jsdom).
import { describe, expect, it } from 'vitest';
import { renderToString } from 'react-dom/server';
import { NextIntlClientProvider } from 'next-intl';
import type { ReactElement } from 'react';
import { messages, type Locale } from '../../i18n';
import { fixtureData, FIXTURE_NOW as NOW } from '../../console/fixture';
import type { StaffClaims } from '../../console/types';
import { Providers } from '../Providers';
import { AuditViewer } from './AuditViewer';
import { ConsoleProvider } from './ConsoleProvider';
import { ConsoleShell, isCurrentConsolePath } from './ConsoleShell';
import { GrantBanner } from './GrantBanner';
import { GrantsScreen } from './GrantsScreen';
import { TenantList } from './TenantList';

const claims = (roles: string[], over: Partial<StaffClaims> = {}): StaffClaims => ({ realm: 'staff', staffId: 'staff-fixture-1', roles, mfaSatisfied: true, sessionVersion: 1, ...over });
// Bare render: any locale, no shell (the shell needs the Arabic-first Providers).
const bare = (node: ReactElement, c: StaffClaims | null, locale: Locale = 'en', tenant: string | null = null, nowOver?: number) =>
  renderToString(
    <div dir={locale === 'ar' ? 'rtl' : 'ltr'}>
      <NextIntlClientProvider locale={locale} messages={messages[locale]} timeZone="UTC">
        <ConsoleProvider claims={c} currentSessionVersion={1} assumeAudited data={fixtureData(NOW)} now={nowOver ?? NOW} initialTenantId={tenant}>
          {node}
        </ConsoleProvider>
      </NextIntlClientProvider>
    </div>,
  );
// Shell render: Providers starts in Arabic (rtl) like the real app.
const shell = (node: ReactElement, c: StaffClaims | null) =>
  renderToString(
    <div dir="rtl">
      <Providers>
        <ConsoleProvider claims={c} currentSessionVersion={1} assumeAudited now={NOW}>
          <ConsoleShell>{node}</ConsoleShell>
        </ConsoleProvider>
      </Providers>
    </div>,
  );

describe('team console', () => {
  it('denies without a staff session and renders no navigation or data', () => {
    for (const c of [null, claims(['owner'], { realm: 'customer' }), claims(['owner'], { mfaSatisfied: false }), claims(['nope']), claims(['owner'], { sessionVersion: 0 })]) {
      const out = shell(<TenantList />, c);
      expect(out).toContain(messages.ar.console.denied.title);
      expect(out).not.toContain('<nav');
      expect(out).not.toContain('Sample Trading Co');
    }
  });
  it('lists tenant metadata in both languages with one main landmark and no inline physical styles', () => {
    for (const l of ['en', 'ar'] as const) {
      const out = bare(<TenantList />, claims(['support']), l);
      expect(out).toContain('Sample Trading Co');
      expect(out).toContain(messages[l].console.tenants.title);
      for (const m of out.matchAll(/style="([^"]*)"/g)) expect(m[1]).not.toMatch(/(?:^|[;\s-])(?:left|right)\s*:|text-align|float/i);
    }
    const full = shell(<TenantList />, claims(['support']));
    expect(full.match(/<main/g)).toHaveLength(1);
    expect(full).toContain('dir="rtl"');
  });
  it('shows the grant banner with time left only inside a tenant under a live grant', () => {
    const inTenant = bare(<GrantBanner />, claims(['owner']), 'en', 'tenant-fixture-a');
    expect(inTenant).toContain('You are inside Sample Trading Co under a support grant');
    expect(inTenant).toContain('00:35:00');
    expect(bare(<GrantBanner />, claims(['owner']), 'en', 'tenant-fixture-b')).not.toContain('under a support grant');
    expect(bare(<GrantBanner />, claims(['owner']), 'en')).not.toContain('under a support grant');
    // after expiry the stay is over, and a revoked grant never shows one
    expect(bare(<GrantBanner />, claims(['owner']), 'en', 'tenant-fixture-a', NOW + 2100)).not.toContain('under a support grant');
    expect(bare(<GrantBanner />, claims(['owner']), 'en', 'tenant-fixture-d')).not.toContain('under a support grant');
  });
  it('keeps the ticking clock out of the live region', () => {
    const out = bare(<GrantBanner />, claims(['owner']), 'en', 'tenant-fixture-a');
    expect(out).toContain('role="status"');
    expect(out).toMatch(/role="timer"[^>]*aria-live="off"|aria-live="off"[^>]*role="timer"/);
    expect(bare(<GrantBanner />, claims(['owner']), 'en', 'tenant-fixture-a', NOW + 1600)).toContain(messages.en.console.banner.low);
    expect(out).not.toContain(messages.en.console.banner.low);
  });
  it('waits for the view audit before showing any data', () => {
    const pending = renderToString(
      <NextIntlClientProvider locale="en" messages={messages.en} timeZone="UTC">
        <ConsoleProvider claims={claims(['owner'])} currentSessionVersion={1} now={NOW}>
          <TenantList />
        </ConsoleProvider>
      </NextIntlClientProvider>,
    );
    expect(pending).toContain(messages.en.console.viewAudit.pending);
    expect(pending).not.toContain('Sample Trading Co');
  });
  it('shows grant sections with a countdown and no staff approve or revoke', () => {
    const owner = bare(<GrantsScreen />, claims(['owner']));
    expect(owner).toContain('00:35:00');
    expect(owner).toContain(messages.en.console.grants.awaitingApproval);
    expect(owner).not.toContain('>Approve<');
    expect(owner).not.toContain('>Revoke<');
    expect(owner).toContain(messages.en.console.grants.newTitle);
    const sec = bare(<GrantsScreen />, claims(['security']));
    expect(sec).not.toContain(messages.en.console.grants.newTitle);
    expect(sec).not.toContain('>Approve<');
  });
  it('audit viewer is limited for support and complete for security', () => {
    expect(bare(<AuditViewer />, claims(['security']))).toContain('tenant-fixture-b');
    expect(bare(<AuditViewer />, claims(['support'], { staffId: 'staff-fixture-2' }))).not.toContain('tenant-fixture-d');
    expect(bare(<AuditViewer />, claims(['support'], { staffId: 'staff-fixture-2' }))).toContain('Example Foods');
  });
  it('marks the staff realm on every console page, also when access is denied (WEB-029)', () => {
    const ok = shell(<TenantList />, claims(['support']));
    expect(ok).toContain('data-realm="staff"');
    expect(ok).toContain(messages.ar.console.realm.label);
    const denied = shell(<TenantList />, null);
    expect(denied).toContain('data-realm="staff"');
    expect(denied).toContain(messages.ar.console.realm.label);
  });
  it('the current console page is marked in the navigation', () => {
    expect(isCurrentConsolePath('/console/', '/console/')).toBe(true);
    expect(isCurrentConsolePath('/console/', '/console')).toBe(true);
    expect(isCurrentConsolePath('/console/', '/console/audit/')).toBe(false);
    expect(isCurrentConsolePath('/console/audit/', '/console/audit')).toBe(true);
    expect(isCurrentConsolePath('/console/grants/', '/console/audit/')).toBe(false);
    expect(isCurrentConsolePath('/console/grants/', '')).toBe(false);
  });
  it('navigation shows only what the role may open', () => {
    const out = shell(<TenantList />, claims(['support']));
    expect(out).toContain('/console/grants');
    expect(out).toContain('/console/audit');
    // negative: an unknown role is denied and gets no navigation
    const unknown = shell(<TenantList />, claims(['guest']));
    expect(unknown).not.toContain('/console/grants');
    expect(unknown).not.toContain('<nav');
  });
  it('translates language labels, plan names and survives an unknown region', () => {
    const out = shell(<TenantList />, claims(['support']));
    expect(out).toContain(messages.ar.console.languageName.en);
    expect(bare(<TenantList />, claims(['support']), 'en')).toContain('Growth');
  });
  it('never names the engine in visible text', () => {
    const word = new RegExp(['fra', 'ppe|erp', 'next'].join(''), 'i');
    for (const l of ['en', 'ar'] as const) expect(JSON.stringify(messages[l].console)).not.toMatch(word);
  });
});
