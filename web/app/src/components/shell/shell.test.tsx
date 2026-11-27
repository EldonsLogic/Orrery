// WEB-003: server-render the shell in rtl and ltr (same approach as ui/rtl.test.tsx; no jsdom).
import { describe, expect, it } from 'vitest';
import { renderToString } from 'react-dom/server';
import type { ReactElement } from 'react';
import { messages } from '../../i18n';
import { fixtureSession, type SessionState } from '../../lib/session';
import { Providers } from '../Providers';
import { AppShell } from './AppShell';
import { HomeView } from './HomeView';
import { SessionProvider } from './SessionProvider';
import { lockupMarkup } from './BrandLockup';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

// Providers starts in the default locale (Arabic) and reads the stored language only after mount.
const ar = messages.ar.shell;
const render = (node: ReactElement | null, initial?: SessionState) =>
  renderToString(
    <div dir="rtl">
      <Providers>
        <SessionProvider initial={initial}>
          <AppShell>{node}</AppShell>
        </SessionProvider>
      </Providers>
    </div>,
  );

describe('app shell (Arabic, rtl)', () => {
  it('has a skip link, one main landmark, a labelled nav and a workspace switcher', () => {
    const out = render(<HomeView />);
    expect(out).toContain('href="#main"');
    expect(out.match(/<main/g)).toHaveLength(1);
    expect(out).toContain(`aria-label="${ar.nav.label}"`);
    expect(out).toContain('Sample Trading Co');
    expect(out).toContain('(موقوفة)');
    expect(out).toContain('aria-expanded="false"');
    expect(out.startsWith('<div dir="rtl"')).toBe(true);
    for (const m of out.matchAll(/style="([^"]*)"/g)) expect(m[1]).not.toMatch(/(?:^|[;\s-])(?:left|right)\s*:|text-align|float/i);
  });
  it('shows only what the active roles allow', () => {
    expect(render(<HomeView />)).toContain('أوامر البيع');
    const none: SessionState =
      fixtureSession.status === 'ready' ? { ...fixtureSession, claims: { ...fixtureSession.claims, roles: [] } } : fixtureSession;
    const out = render(<HomeView />, none);
    expect(out).not.toContain('أوامر البيع');
    expect(out).toContain(ar.home.emptyTitle);
  });
  it('renders signed-out, error and loading states without the navigation', () => {
    expect(render(null, { status: 'signedOut' })).toContain(ar.state.signedOut.title);
    expect(render(null, { status: 'error' })).toContain(ar.state.error.retry);
    const loading = render(null, { status: 'loading' });
    expect(loading).toContain(ar.state.loading);
    expect(loading).not.toContain('<nav');
  });
  it('keeps the language storage key in one place (firstPaint)', () => {
    const src = readFileSync(join(__dirname, '../Providers.tsx'), 'utf8');
    expect(src).not.toContain("'platform.locale.v1'");
    expect(src).toContain('LOCALE_STORAGE_KEY');
  });
  it('never names the engine in visible text', () => {
    const word = new RegExp(['fra', 'ppe|erp', 'next'].join(''), 'i');
    for (const l of ['en', 'ar'] as const) expect(JSON.stringify(messages[l].shell)).not.toMatch(word);
  });
});

describe('shell chrome (WEB-029)', () => {
  const read = (rel: string) => readFileSync(join(__dirname, rel), 'utf8');
  it('builds the lockup from the logo file with token colours and no hex', () => {
    const out = lockupMarkup(read('../../../../../docs/brand/logo/lockup-primary.svg'));
    expect(out).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
    expect(out.match(/data-part="mark"/g)).toHaveLength(1);
    expect(out.match(/data-part="word"/g)).toHaveLength(1);
    expect(out).toContain('aria-hidden="true"');
  });
  it('keeps Ask Seshna one tap away with the Latin name isolated', () => {
    const out = render(<HomeView />);
    expect(out).toContain(`aria-label="${ar.dock.label}"`);
    expect(out).toMatch(/class="[^"]*dockLink[^"]*" href="\/chat\/?"/);
    expect(out).toContain('<bdi>Seshna</bdi>');
  });
  it('switches company through a labelled button and listbox, with suspended workspaces disabled', () => {
    const out = render(<HomeView />);
    expect(out).toMatch(/<button[^>]*aria-haspopup="listbox"[^>]*aria-expanded="false"/);
    expect(out).toMatch(/<ul[^>]*role="listbox"[^>]*hidden=""/);
    expect(out.match(/role="option"/g)).toHaveLength(3);
    expect(out).toMatch(/role="option" aria-selected="true"[^>]*>(?:(?!<\/li>).)*Sample Trading Co/);
    expect(out).toMatch(/aria-disabled="true"[^>]*>(?:(?!<\/li>).)*\(موقوفة\)/);
    expect(out).not.toContain('<select');
  });
  it('has a visible language switch with Arabic pressed by default', () => {
    const out = render(<HomeView />);
    expect(out).toContain(`role="group" aria-label="${ar.language.label}"`);
    expect(out).toMatch(/lang="ar" dir="rtl"[^>]*aria-pressed="true"[^>]*>عربي</);
    expect(out).toMatch(/lang="en" dir="ltr"[^>]*aria-pressed="false"[^>]*>English</);
  });
  it('shows the account as a round avatar with an accessible name', () => {
    const out = render(<HomeView />);
    expect(out).toMatch(/aria-label="[^"]*Sample Person[^"]*"[^>]*><span aria-hidden="true">SP<\/span>/);
  });
  it('gives every navigation item an icon and shows the plan status at the bottom', () => {
    const out = render(<HomeView />);
    const nav = out.slice(out.indexOf('<nav aria-label="' + ar.nav.label));
    const links = nav.slice(0, nav.indexOf('</nav>')).match(/<a [^>]*>/g) ?? [];
    expect(links.length).toBeGreaterThan(3);
    expect(nav.match(/<a [^>]*><svg[^>]*aria-hidden="true"/g)).toHaveLength(links.length);
    expect(nav).toContain(messages.ar.marks.progress.title);
    expect(nav).toContain(messages.ar.marks.progress.stage.live);
  });
  it('uses glass only through the foundation variables, with a solid drawer', () => {
    const sheet = read('Shell.module.css');
    expect(sheet.match(/(?:-webkit-)?backdrop-filter: var\(--glass-filter\)/g)).toHaveLength(6); // top bar, side navigation, dock; each with the -webkit- copy
    expect(sheet).not.toMatch(/backdrop-filter: (?!var)/);
    expect(sheet).toMatch(/\.navWrap\[data-open='true'\] \{[^}]*background: var\(--color-surface\)/);
  });
});
