import { fixtureRequests } from './fixture';
import type { ComponentRequestRecord, ReviewCommand } from './types';

/**
 * The only way the review screens read or change anything. ChatPort-style: an injected interface, a fixture
 * implementation so the screens work with no backend, and nothing else. REAL WIRING GOES HERE (a later row, through the
 * gateway with the staff token): list reads `ComponentRequests.list()`, act calls `attest_risk_class`,
 * `attest_generalisable`, `approve` or `reject` as the verified staff user. The SERVER enforces who may act, separation of
 * duties, the reviewer role, the money-field rule and MFA step-up (ADR-0047, ADR-0048). The screens only show a guess of
 * the outcome so that people are not offered buttons that are certain to fail.
 */
export type ActCode = 'not_wired' | 'step_up_required' | 'forbidden' | 'unavailable' | (string & {});
export type ListResult =
  | { ok: true; minTenants: number; requests: ReadonlyArray<ComponentRequestRecord> }
  | { ok: false; code: ActCode };
export type ActResult = { ok: true } | { ok: false; code: ActCode };

export type FactoryReviewPort = {
  list: () => Promise<ListResult>;
  act: (cmd: ReviewCommand) => Promise<ActResult>;
};

/** Fixture port: synthetic records, and an action that NEVER executes (fixed result, stores and logs nothing). */
export const fixturePort: FactoryReviewPort = {
  list: async () => ({ ok: true, minTenants: 2, requests: fixtureRequests }),
  act: async () => ({ ok: false, code: 'not_wired' }),
};
