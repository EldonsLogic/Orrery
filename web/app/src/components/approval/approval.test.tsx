// WEB-027: server-render the owner approval screen in both languages (same approach as blueprint.test.tsx; no jsdom).
import { describe, expect, it } from 'vitest';
import { renderToString } from 'react-dom/server';
import { NextIntlClientProvider } from 'next-intl';
import { messages } from '../../i18n';
import { buildRequest, emptyForm, formKey, nextStatus, submitDecision, type Form } from '../../approval/decide';
import { messagePath, percentText } from '../../approval/labels';
import { regionName } from '../../blueprint/format';
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
  for: formKey(fixtureReview), decision, reason: decision === 'approve' ? 'agree' : decision === 'reject' ? 'other' : 'unclear', note: '', confirmed: ALL, ...over,
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
    expect(fixtureBlockedReview.canDecide).toBe(true); // a state the model emits: too_large stops approval only
    expect(out).toContain(messages.en.ownerApproval.blocker.too_large);
  });
  it('shows the form for an allowed choice and hides it for a blocked one', () => {
    expect(page(fixtureReview, 'en', 'approve')).toContain(messages.en.ownerApproval.ui.confirmHeading);
    expect(page(fixtureBlockedReview, 'en', 'approve')).not.toContain(messages.en.ownerApproval.ui.confirmHeading);
  });
  it('shows the VAT line, the tax setup and the counts from the model', () => {
    const out = page(fixtureReview, 'en');
    expect(out).toContain('VAT 15%');
    expect(out).toContain(messages.en.ownerApproval.ui.vatRegistered);
    expect(out).toContain(messages.en.ownerApproval.ui.mode.zatca_phase1);
    expect(out).toContain(messages.en.ownerApproval.ui.country);
    expect(page(fixtureReview, 'ar')).toContain(messages.ar.ownerApproval.ui.eInvoicing);
  });
  it('isolates item names, quote parameters and unpriced text, and marks a shortened name', () => {
    const out = page(fixtureReview, 'en');
    expect(out).toMatch(/<bdi[^>]*>Customer<\/bdi>/);
    expect(out).toContain('\u2068core.crm\u2069');
    const cut = { ...fixtureReview, sections: fixtureReview.sections.map((s) => (s.id === 'summary' ? { ...s, items: s.items.map((it, i) => (i ? it : { ...it, labels: { ...it.labels, cut: true } })) } : s)) } as ReviewModel;
    expect(page(cut, 'en')).toContain(messages.en.ownerApproval.ui.cut);
  });
  it('says unavailable, not an error, for a label key it does not know', () => {
    const odd = { ...fixtureReview, introKey: 'oa.nope' } as ReviewModel;
    expect(page(odd, 'en')).toContain(messages.en.ownerApproval.ui.unknownLabel);
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
  it('needs the three confirmations only to approve (Q-585)', async () => {
    const port = fakePort();
    expect(buildRequest(fixtureReview, form('approve', { confirmed: [] }))).toBeNull();
    for (const d of ['reject', 'request_changes'] as const) {
      expect(await submitDecision(port, fixtureReview, form(d, { confirmed: [] }))).toEqual({ ok: true });
    }
    expect(port.calls.map((c) => c.confirmations)).toEqual([[], []]);
    const out = page(fixtureReview, 'en', 'reject');
    expect(out).not.toContain(messages.en.ownerApproval.ui.confirmHeading);
    expect(page(fixtureReview, 'en', 'request_changes')).not.toContain(messages.en.ownerApproval.ui.confirmHeading);
    expect(page(fixtureReview, 'en', 'approve')).toContain(messages.en.ownerApproval.ui.confirmHeading);
  });
  it('sends nothing without all three confirmations (approve), a listed reason, or inside the note limit', async () => {
    const port = fakePort();
    for (const f of [form('approve', { confirmed: ALL.slice(1) }), form('approve', { confirmed: [] }), form('approve', { reason: '' }), form('reject', { reason: 'agree' }),
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

describe('owner approval form and status', () => {
  it('a form made for another view never sends, so old ticks cannot go out with new digests', async () => {
    const f = form('approve', { note: 'seen' });
    const next = { ...fixtureReview, quoteDigest: 'f'.repeat(64) };
    expect(formKey(next)).not.toBe(formKey(fixtureReview));
    expect(buildRequest(next, f)).toBeNull();
    expect(buildRequest({ ...fixtureReview, blueprintDigest: 'e'.repeat(64) }, f)).toBeNull();
    const port = fakePort();
    expect(await submitDecision(port, next, f)).toEqual({ ok: false, code: 'OA-001' });
    expect(port.calls).toHaveLength(0);
    expect(emptyForm(next, 'approve')).toMatchObject({ for: formKey(next), confirmed: [], note: '', reason: 'agree' });
    expect(emptyForm(next, 'reject').reason).toBe('');
  });
  it('puts the chosen reason and note in the request', () => {
    expect(buildRequest(fixtureReview, form('request_changes', { reason: 'wrong_price', note: 'n' }))).toMatchObject({ reason: 'wrong_price', note: 'n', decision: 'request_changes' });
  });
  it('holds the note at its limit and requires one only where the model says so', () => {
    const n = fixtureReview.noteLimit;
    expect(buildRequest(fixtureReview, form('reject', { note: 'x'.repeat(n) }))).not.toBeNull();
    expect(buildRequest(fixtureReview, form('reject', { note: 'x'.repeat(n + 1) }))).toBeNull();
    const need = { ...fixtureReview, decisions: fixtureReview.decisions.map((d) => (d.key === 'reject' ? { ...d, noteRequired: true } : d)) };
    expect(buildRequest(need, form('reject'))).toBeNull();
    expect(buildRequest(need, form('reject', { note: '   ' }))).toBeNull();
    expect(buildRequest(need, form('reject', { note: 'why' }))).not.toBeNull();
  });
  it('checks each decision own allowed flag, apart from canDecide', () => {
    const only = (key: DecisionKey, over: object): ReviewModel => ({ ...fixtureReview, decisions: fixtureReview.decisions.map((d) => (d.key === key ? { ...d, ...over } : d)) });
    expect(buildRequest(only('approve', { allowed: false }), form('approve'))).toBeNull(); // canDecide stays true
    expect(buildRequest(only('reject', { allowed: false }), form('reject'))).toBeNull();
    expect(buildRequest({ ...fixtureReview, canDecide: false }, form('approve'))).toBeNull();
    expect(buildRequest(fixtureReview, form('reject'))).not.toBeNull();
  });
  it('shows recorded only for an ok result, and locks the form after OA-006', () => {
    expect(nextStatus({ ok: true })).toEqual({ kind: 'done' });
    expect(nextStatus({ ok: false, code: 'OA-015' })).toEqual({ kind: 'error', code: 'OA-015' });
    expect(nextStatus({ ok: false, code: 'generic' })).toEqual({ kind: 'error', code: 'generic' });
    expect(nextStatus({ ok: false, code: 'OA-006' })).toEqual({ kind: 'stale' });
  });
  it('maps view-model label keys to message paths', () => {
    expect(messagePath('oa.summary.not_shown')).toBe('summary.not_shown_notice');
    expect(messagePath('oa.summary.not_shown.branding')).toBe('summary.not_shown.branding');
    expect(messagePath('oa.state.awaiting')).toBe('state.awaiting');
    expect(messagePath('quote.line.module')).toBe('quote.line.module');
  });
  it('formats basis points as a percent', () => {
    const rows: Array<[number, string]> = [[0, '0'], [5, '0.05'], [50, '0.5'], [1405, '14.05'], [1450, '14.5'], [1500, '15'], [10000, '100']];
    for (const [bp, text] of rows) expect(percentText(bp)).toBe(text);
  });
});

describe('owner approval compliance row', () => {
  const withCompliance = (c: object) => ({ ...fixtureReview, sections: fixtureReview.sections.map((s) => (s.id === 'summary' ? { ...s, compliance: { ...s.compliance, ...c } } : s)) }) as ReviewModel;
  it('hides the country row for an empty or malformed code instead of throwing', () => {
    for (const country of ['', 'sa', 'SAU', '1!', 'S']) {
      const out = page(withCompliance({ country }), 'en');
      expect(out).not.toContain(messages.en.ownerApproval.ui.country);
    }
    expect(page(withCompliance({ country: 'AE' }), 'en')).toContain('United Arab Emirates');
  });
  it('regionName falls back to the code for a malformed one', () => {
    expect(regionName('zz1', 'en')).toBe('zz1');
    expect(regionName('', 'en')).toBe('');
    expect(regionName('SA', 'en')).toBe('Saudi Arabia');
  });
  it('names every e-invoicing contract value in both languages, and an unknown one neutrally', () => {
    for (const mode of ['none', 'zatca_phase1', 'zatca_phase2', 'uae_e_invoicing', 'eg_e_invoice']) {
      for (const l of ['en', 'ar'] as const) {
        const label = (messages[l].ownerApproval.ui.mode as Record<string, string>)[mode];
        expect(label, `${l} ${mode}`).toBeTruthy();
        const out = page(withCompliance({ eInvoicingMode: mode }), l);
        expect(out).toContain(label);
        expect(out).not.toContain(mode);
      }
    }
    expect(page(withCompliance({ eInvoicingMode: 'made_up' }), 'en')).not.toContain('made_up');
    expect(fixtureReview.sections[0]).toMatchObject({ compliance: { eInvoicingMode: 'zatca_phase1' } });
  });
  it('joins lists with the locale list format', () => {
    const en = page(fixtureReview, 'en');
    expect(en).toContain('Record 1, Process 1, and Job role 1');
    expect(en).toContain('Logo and colours and Language settings');
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
