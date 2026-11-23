// WEB-027: server-render the owner approval screen in both languages (same approach as blueprint.test.tsx; no jsdom).
import { describe, expect, it } from 'vitest';
import { renderToString } from 'react-dom/server';
import { NextIntlClientProvider } from 'next-intl';
import { messages } from '../../i18n';
import { buildRequest, submitDecision, type Form } from '../../approval/decide';
import { INJECTION, fakePort, fixtureBlockedReview, fixtureInjectionReview, fixtureReview } from '../../approval/fixture';
import type { DecisionKey, ReviewModel } from '../../approval/types';
import { OwnerApprovalView } from './OwnerApprovalView';

const ENGINE = new RegExp(['fra' + 'ppe', 'ERP' + 'Next'].join('|'), 'i');
const page = (view: ReviewModel, locale: 'ar' | 'en', choice: DecisionKey | null = null) =>
  renderToString(
    <div dir={locale === 'ar' ? 'rtl' : 'ltr'}>
      <NextIntlClientProvider locale={locale} messages={messages[locale]}>
        <OwnerApprovalView view={view} port={fakePort()} initialChoice={choice} />
      </NextIntlClientProvider>
    </div>,
  );
const ALL = fixtureReview.confirmations.map((c) => c.key);
const form = (decision: DecisionKey, over: Partial<Form> = {}): Form => ({
  decision, reason: decision === 'approve' ? 'agree' : decision === 'reject' ? 'other' : 'unclear', note: '', confirmed: ALL, ...over,
});

describe('owner approval screen', () => {
  it('renders summary, price, gaps, test month and the three actions in Arabic and English', () => {
    for (const l of ['ar', 'en'] as const) {
      const out = page(fixtureReview, l);
      const t = messages[l].ownerApproval;
      expect(out.match(/<h1/g)).toHaveLength(1);
      for (const id of ['summary', 'cost', 'gaps', 'simulation', 'decide']) expect(out).toContain(`id="oa-${id}"`);
      for (const s of [t.title, t.section.cost, t.decision.approve, t.decision.request_changes, t.decision.reject, t.sim.check.month_end]) expect(out).toContain(s);
      expect(out).toContain('SAR 2645.00'); // finished by the model, not added here
      expect(out).toContain(l === 'ar' ? 'شركة العينة للتجارة' : 'Sample Trading Co');
      expect(out).not.toMatch(ENGINE);
    }
  });
  it('shows the notice that some details are not listed, and the draft price notice', () => {
    const out = page(fixtureReview, 'en');
    expect(out).toContain(messages.en.ownerApproval.cost.not_binding);
    expect(out).toContain(messages.en.ownerApproval.summary.not_shown.branding);
  });
  it('is right-to-left safe: numbers and names are isolated, no physical-direction markup', () => {
    const out = page(fixtureReview, 'ar');
    expect(out).toContain('dir="rtl"');
    expect(out).toContain('<bdi dir="ltr"');
    expect(out).not.toMatch(/\b(left|right)\b\s*:/);
  });
  it('disables approve when the model says approval is not allowed, and keeps reject open', () => {
    const out = page(fixtureBlockedReview, 'en');
    const btn = (label: string) => new RegExp(`<button[^>]*>${label}</button>`).exec(out)?.[0] ?? '';
    expect(btn(messages.en.ownerApproval.decision.approve)).toContain('disabled=""');
    expect(btn(messages.en.ownerApproval.decision.reject)).not.toContain('disabled');
    expect(out).toContain(messages.en.ownerApproval.blocker.too_large);
  });
  it('shows the form for an allowed choice and hides it for a blocked one', () => {
    expect(page(fixtureReview, 'en', 'approve')).toContain(messages.en.ownerApproval.ui.confirmHeading);
    expect(page(fixtureBlockedReview, 'en', 'approve')).not.toContain(messages.en.ownerApproval.ui.confirmHeading);
  });
  it('renders untrusted text as plain text', () => {
    for (const l of ['ar', 'en'] as const) {
      const out = page(fixtureInjectionReview, l);
      expect(out).not.toContain('<img');
      expect(out).not.toContain('<script');
      expect(out).toContain('&lt;img src=x onerror=&quot;alert(1)&quot;&gt;');
      expect(out).toContain('{rate}'); // not read as a message placeholder
    }
    expect(INJECTION).toContain('<script>');
  });
});

describe('owner approval decisions', () => {
  it('emits each decision through the port with the digests the owner saw', async () => {
    const port = fakePort();
    for (const d of ['approve', 'request_changes', 'reject'] as const) expect(await submitDecision(port, fixtureReview, form(d, { note: 'ok' }))).toEqual({ ok: true });
    expect(port.calls.map((c) => c.decision)).toEqual(['approve', 'request_changes', 'reject']);
    expect(port.calls[0]).toMatchObject({
      tenantId: fixtureReview.tenantId, blueprintId: fixtureReview.blueprintId, seenBlueprintDigest: fixtureReview.blueprintDigest,
      seenQuoteDigest: fixtureReview.quoteDigest, confirmations: ALL, note: 'ok',
    });
  });
  it('sends nothing without all three confirmations, a listed reason, or inside the note limit', async () => {
    const port = fakePort();
    for (const f of [form('approve', { confirmed: ALL.slice(1) }), form('approve', { reason: '' }), form('reject', { reason: 'agree' }),
      form('reject', { note: 'x'.repeat(fixtureReview.noteLimit + 1) })]) {
      expect(buildRequest(fixtureReview, f)).toBeNull();
      expect(await submitDecision(port, fixtureReview, f)).toEqual({ ok: false, code: 'OA-001' });
    }
    expect(port.calls).toHaveLength(0);
  });
  it('never sends an approval the model does not allow', async () => {
    const port = fakePort();
    expect(await submitDecision(port, fixtureBlockedReview, form('approve'))).toEqual({ ok: false, code: 'OA-001' });
    expect(await submitDecision(port, { ...fixtureReview, canDecide: false }, form('approve'))).toEqual({ ok: false, code: 'OA-001' });
    expect(port.calls).toHaveLength(0);
    expect(await submitDecision(port, fixtureBlockedReview, form('reject'))).toEqual({ ok: true });
  });
  it('returns a refusal code from the port and survives a failing port', async () => {
    expect(await submitDecision(fakePort({ ok: false, code: 'OA-006' }), fixtureReview, form('approve'))).toEqual({ ok: false, code: 'OA-006' });
    const bad = { decide: async () => { throw new Error('down'); } };
    expect(await submitDecision(bad, fixtureReview, form('approve'))).toEqual({ ok: false, code: 'generic' });
  });
});

describe('owner approval messages', () => {
  const flat = (o: unknown, p = ''): string[] =>
    Object.entries(o as Record<string, unknown>).flatMap(([k, v]) => (typeof v === 'object' && v !== null ? flat(v, `${p}${k}.`) : [`${p}${k}`]));
  it('covers every label key the model can emit, in both languages', () => {
    const keys = new Set<string>();
    const walk = (o: unknown) => {
      if (Array.isArray(o)) o.forEach(walk);
      else if (o && typeof o === 'object') {
        for (const [k, v] of Object.entries(o)) {
          if (typeof v === 'string' && /Key$|^labelKey$/.test(k)) keys.add(v);
          else walk(v);
        }
      }
    };
    walk(fixtureReview);
    for (const l of ['ar', 'en'] as const) {
      const have = new Set(flat(messages[l].ownerApproval));
      for (const k of keys) expect(have.has(k === 'oa.summary.not_shown' ? 'summary.not_shown_notice' : k.replace(/^oa\./, '')), `${l} ${k}`).toBe(true);
      for (const code of ['OA-006', 'OA-014', 'OA-015', 'OA-018', 'generic']) expect(have.has(`error.${code}`)).toBe(true);
    }
  });
});
