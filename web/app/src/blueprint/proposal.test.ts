// WEB-029: the proposal around the Blueprint (modules, gaps, draft price) and the approval checklist. Pure.
import { describe, expect, it } from 'vitest';
import { buildProposalView, canApprove, CONFIRMATIONS } from './proposal';
import { fixtureProposal } from './fixture/proposal';

describe('proposal view', () => {
  it('lists every module with its status and counts the approved ones', () => {
    const v = buildProposalView(fixtureProposal, 'en');
    expect(v.modules.length).toBe(fixtureProposal.modules.length);
    expect(v.approved).toBe(fixtureProposal.modules.filter((m) => m.status === 'approved').length);
    for (const m of v.modules) expect(['drafted', 'approved']).toContain(m.status);
  });
  it('uses the reader language and never falls back to an internal id', () => {
    const ar = buildProposalView(fixtureProposal, 'ar');
    for (const m of ar.modules) expect(m.label).not.toBe(m.id);
    expect(ar.modules[0]!.label).toBe(fixtureProposal.modules[0]!.labels.ar);
    const bare = buildProposalView({ ...fixtureProposal, modules: [{ ...fixtureProposal.modules[0]!, labels: {} }] }, 'ar');
    expect(bare.modules[0]!.label).toBe('');
  });
  it('puts uncovered gaps before partly covered ones', () => {
    const v = buildProposalView(fixtureProposal, 'en');
    expect(v.gaps.length).toBe(fixtureProposal.gaps.length);
    const first = v.gaps.findIndex((g) => g.status === 'partial');
    const lastUncovered = v.gaps.map((g) => g.status).lastIndexOf('uncovered');
    if (first >= 0 && lastUncovered >= 0) expect(lastUncovered).toBeLessThan(first);
  });
  it('shows the price as the quote gives it (decimal strings, no maths) and hides it when a figure is missing', () => {
    const v = buildProposalView(fixtureProposal, 'en');
    expect(v.price).not.toBeNull();
    expect(v.price!.monthly.total).toEqual({ value: fixtureProposal.price.monthly.total, currency: fixtureProposal.price.currency });
    const broken = buildProposalView(
      { ...fixtureProposal, price: { ...fixtureProposal.price, monthly: { ...fixtureProposal.price.monthly, total: '' } } },
      'en',
    );
    expect(broken.price).toBeNull();
  });
});

describe('approval checklist', () => {
  it('needs all three confirmations', () => {
    expect(canApprove(new Set())).toBe(false);
    expect(canApprove(new Set(['summary', 'quote']))).toBe(false);
    expect(canApprove(new Set(CONFIRMATIONS))).toBe(true);
  });
});
