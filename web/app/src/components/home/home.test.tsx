// WEB-029: the owner home renders from fixtures in both languages, scoped by role, with tokens only.
import { describe, expect, it } from 'vitest';
import { renderToString } from 'react-dom/server';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { NextIntlClientProvider } from 'next-intl';
import { messages, type Locale } from '../../i18n';
import { liveHome, simulatingHome } from '../../home/fixture';
import { fixtureHomePort, scopeOverview } from '../../home/port';
import type { HomeOverview } from '../../home/types';
import { HomeScreen } from './HomeScreen';

const shortcuts = [{ id: 'sales_order', label: 'Sales orders', href: '/records/sales_order/' }];
const render = (data: HomeOverview | null, locale: Locale = 'en', loading = false) =>
  renderToString(
    <div dir={locale === 'ar' ? 'rtl' : 'ltr'}>
      <NextIntlClientProvider locale={locale} messages={messages[locale]} timeZone="UTC">
        <HomeScreen data={data} loading={loading} company="Sample Trading Co" person="Sample Person" shortcuts={shortcuts} />
      </NextIntlClientProvider>
    </div>,
  );
const text = (html: string) => html.replace(/<[^>]+>/g, '').replace(/&#x27;/g, "'");

describe('owner home (live)', () => {
  it('shows the greeting, company, date and live status', () => {
    const out = text(render(liveHome));
    expect(out).toContain('Welcome back, Sample Person');
    expect(out).toContain('Sample Trading Co');
    expect(out).toContain('Thursday, November 26, 2026');
    expect(out).toContain(messages.en.home.status.live);
    expect(out).toContain(messages.en.home.today.title);
    expect(out).not.toContain(messages.en.home.journey.title);
  });
  it('renders four KPI tiles with Western digits, the currency code and a word beside every change', () => {
    const out = text(render(liveHome));
    for (const k of ['sales_month', 'receivables', 'awaiting_approval', 'cash'] as const) expect(out).toContain(messages.en.home.kpis[k]);
    expect(out).toContain('482,350SAR');
    expect(out).toContain('Up 12.4% on last month');
    expect(out).toContain('Down 3.1% on last month');
    expect(out).toContain('3 overdue');
    expect(out).toContain('Oldest waiting 2 days');
  });
  it('lists each approval as drafted by the AI with a review action', () => {
    const html = render(liveHome);
    expect(html.match(/data-status="drafted"/g)).toHaveLength(liveHome.approvals.length);
    expect(html).toContain('aria-label="Review Purchase order PO\u20110142"');
    expect(text(html)).toContain('Nothing posts until you approve.');
  });
  it('groups activity by day and isolates the Latin name', () => {
    const out = render(liveHome);
    expect(text(out)).toContain('Riyadh Home Market paid invoice INV\u20110459');
    expect(text(out)).toContain('Yesterday');
    expect(out).toContain('<bdi>Seshna</bdi> drafted 2 supplier payments');
  });
  it('uses one Coral mark, beside the Ask Seshna label', () => {
    const out = render(liveHome);
    expect(out.match(/_accent_/g)).toHaveLength(1);
    expect(out).toContain('role="search"');
  });
});

describe('owner home (not live, Arabic)', () => {
  it('shows the build journey instead of today, labels simulated figures and keeps Western digits', () => {
    const out = render(simulatingHome, 'ar');
    expect(out.startsWith('<div dir="rtl"')).toBe(true);
    expect(out).toContain(messages.ar.home.journey.title);
    expect(out).toContain('aria-current="step"');
    expect(out).toContain(messages.ar.home.kpis.simulated);
    expect(out).not.toContain('id="today-title"');
    expect(out).toContain('مؤسسة الخليج لمواد التغليف');
    expect(out).toContain('482,350');
    expect(out).not.toMatch(/[٠-٩]/);
  });
  it('keeps the header, Ask Seshna and shortcuts while loading', () => {
    const out = render(null, 'ar', true);
    expect(out).toContain(messages.ar.home.loading);
    expect(out).toContain('Sales orders');
    expect(out).not.toContain('id="kpi-title"');
  });
});

describe('home port', () => {
  it('denies money and approvals by default', async () => {
    expect(scopeOverview(liveHome, ['sales_rep']).kpis).toEqual([]);
    expect(scopeOverview(liveHome, []).approvals).toEqual([]);
    expect(scopeOverview(liveHome, ['accountant']).kpis).toHaveLength(4);
    const claims = { personId: 'p', tenantId: 'tenant-fixture-a', roles: ['owner'], mfaSatisfied: true, sessionVersion: 1 };
    expect((await fixtureHomePort.overview(claims))?.buildState).toBe('live');
    expect(await fixtureHomePort.overview({ ...claims, tenantId: 'unknown' })).toBeNull();
  });
});

describe('home styles', () => {
  const sheet = readFileSync(join(__dirname, 'Home.module.css'), 'utf8');
  it('uses glass only on the Ask Seshna entry and tabular figures for numbers', () => {
    expect(sheet.match(/^\s+backdrop-filter: var\(--glass-filter\)/gm)).toHaveLength(1);
    expect(sheet).toMatch(/\.ask \{[^}]*var\(--glass-fill\)/);
    expect(sheet).toMatch(/\.figure \{[^}]*tabular-nums/);
    expect(sheet).not.toMatch(/\b\d+px\b/);
  });
});
