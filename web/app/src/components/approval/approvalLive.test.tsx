// @vitest-environment jsdom
// WEB-027 review fixes: client behaviour (review swap, pending lock) needs a DOM; the other tests render to strings.
import { afterEach, describe, expect, it } from 'vitest';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { NextIntlClientProvider } from 'next-intl';
import { messages } from '../../i18n';
import { fixtureReview } from '../../approval/fixture';
import type { ApprovalPort, DecisionResult, ReviewModel, SummarySection } from '../../approval/types';
import { OwnerApprovalView } from './OwnerApprovalView';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let root: Root | null = null;
let host: HTMLElement | null = null;
afterEach(() => { act(() => root?.unmount()); host?.remove(); root = null; host = null; });

function mount(view: ReviewModel, port: ApprovalPort, locale: 'ar' | 'en' = 'en') {
  host = document.createElement('div');
  document.body.append(host);
  root = createRoot(host);
  const render = (v: ReviewModel) =>
    act(() => root!.render(
      <NextIntlClientProvider locale={locale} messages={messages[locale]}>
        <OwnerApprovalView view={v} port={port} />
      </NextIntlClientProvider>,
    ));
  render(view);
  return { render, text: () => host!.textContent ?? '' };
}
const click = (el: Element) => act(() => { (el as HTMLElement).click(); });
const btn = (label: string) => [...host!.querySelectorAll('button')].find((b) => b.textContent?.includes(label)) as HTMLButtonElement;
const submit = () => {
  click(btn(T.decision.reject));
  const sel = host!.querySelector('select')!;
  act(() => {
    sel.value = 'other';
    sel.dispatchEvent(new Event('change', { bubbles: true }));
  });
  click(btn(T.ui.submit.replace('{decision}', T.decision.reject)));
};
const T = messages.en.ownerApproval;
const next: ReviewModel = { ...fixtureReview, quoteDigest: 'd'.repeat(64) };

function deferredPort() {
  let resolve: (r: DecisionResult) => void = () => {};
  const port: ApprovalPort = { decide: () => new Promise<DecisionResult>((r) => { resolve = r; }) };
  return { port, resolve: (r: DecisionResult) => act(async () => resolve(r)) };
}

describe('owner approval screen: review swap and pending lock', () => {
  it('drops the earlier review status when the review changes while the port answer is still pending', async () => {
    const d = deferredPort();
    const ui = mount(fixtureReview, d.port);
    submit();
    expect(btn(T.decision.reject).disabled).toBe(true); // the call really is pending
    ui.render(next); // new review while the call for the old one is deferred
    await d.resolve({ ok: true });
    expect(ui.text()).not.toContain(T.ui.done);
    expect(ui.text()).not.toContain(T.error['OA-006']);
    expect(btn(T.decision.approve).getAttribute('aria-pressed')).toBe('false');
  });
  it('drops a stale (OA-006) lock when the review changes', async () => {
    const d = deferredPort();
    const ui = mount(fixtureReview, d.port);
    submit();
    await d.resolve({ ok: false, code: 'OA-006' });
    expect(ui.text()).toContain(T.error['OA-006']);
    ui.render(next);
    expect(ui.text()).not.toContain(T.error['OA-006']);
    expect(btn(T.decision.approve).disabled).toBe(false);
  });
  it('disables the decision controls while a submission is pending', async () => {
    const d = deferredPort();
    const ui = mount(fixtureReview, d.port);
    submit();
    for (const k of ['approve', 'request_changes', 'reject'] as const) expect(btn(T.decision[k]).disabled).toBe(true);
    expect(host!.querySelector('select')!.disabled).toBe(true);
    expect(host!.querySelector('input[type="text"], input:not([type])')!.hasAttribute('disabled')).toBe(true);
    await d.resolve({ ok: true });
    expect(ui.text()).toContain(T.ui.done);
  });
});

describe('owner approval screen: item ids and valid-until', () => {
  const twins = (): ReviewModel => ({
    ...fixtureReview,
    sections: fixtureReview.sections.map((s) => {
      if (s.id !== 'summary') return s;
      const sum = s as SummarySection;
      const a = sum.items[0];
      return { ...sum, items: [{ ...a, id: 'cust_alpha' }, { ...a, id: 'cust_beta' }] };
    }),
  });
  it('shows each item id next to its name, so two items with the same label can be told apart', () => {
    for (const l of ['ar', 'en'] as const) {
      const out = mount(twins(), { decide: async () => ({ ok: true }) }, l).text();
      expect(out).toContain('cust_alpha');
      expect(out).toContain('cust_beta');
      expect(out).toContain(messages[l].ownerApproval.ui.itemId);
      act(() => root?.unmount()); host?.remove();
    }
  });
  it('shows the validity as a localized date, time and stated timezone', () => {
    const iso = (fixtureReview.sections.find((s) => s.id === 'cost') as { validUntil: string }).validUntil;
    for (const l of ['ar', 'en'] as const) {
      const expected = new Intl.DateTimeFormat(l, { year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'UTC', timeZoneName: 'short' }).format(new Date(iso));
      const out = mount(fixtureReview, { decide: async () => ({ ok: true }) }, l).text();
      expect(out).toContain(expected);
      expect(expected).toMatch(/UTC|GMT|غرينتش/);
      act(() => root?.unmount()); host?.remove();
    }
  });
});
