# Decision records (ADR index)

Status: accepted
Owner: eldon

One file per architecture, security, contract or product-shaping decision. Copy [TEMPLATE.md](TEMPLATE.md). Never edit an accepted ADR's decision; supersede it with a new one. Earlier strategy-phase decisions are in [../strategy/decisions.md](../strategy/decisions.md).

| ADR | Title | Status |
|---|---|---|
| [ADR-0001-working-codename.md](ADR-0001-working-codename.md) | Working codename Orrery, not cleared | Accepted; superseded by ADR-0066 (working-name rule) |
| [ADR-0002-seed-engine-frappe-erpnext.md](ADR-0002-seed-engine-frappe-erpnext.md) | Seed engine is Frappe + ERPNext, behind an adapter | Accepted |
| [ADR-0003-five-parts-four-contracts.md](ADR-0003-five-parts-four-contracts.md) | Five parts and four contracts | Accepted |
| [ADR-0004-one-chat-role-based-views.md](ADR-0004-one-chat-role-based-views.md) | One chat, anyone chats, role-based views | Accepted |
| [ADR-0005-human-review-gate-free-first.md](ADR-0005-human-review-gate-free-first.md) | Human review gate for first clients; free-first with entitlements built in | Accepted |
| [ADR-0006-tenancy-site-per-tenant.md](ADR-0006-tenancy-site-per-tenant.md) | Tenancy is an isolated site per customer on shared in-country infrastructure | Accepted |
| [ADR-0007-identity.md](ADR-0007-identity.md) | Identity model | Accepted |
| [ADR-0008-no-client-specific-code.md](ADR-0008-no-client-specific-code.md) | No client-specific code; component factory; autonomy metrics | Accepted |
| [ADR-0009-repo-workflow.md](ADR-0009-repo-workflow.md) | Repo workflow | Accepted |
| [ADR-0010-model-strategy.md](ADR-0010-model-strategy.md) | Model strategy | Accepted |
| [ADR-0011-interim-design-system.md](ADR-0011-interim-design-system.md) | Interim design system is brand guidelines v1 (Quadrant); logo is a placeholder | Accepted; partly superseded by ADR-0066 (logo, heading typeface) |
| [ADR-0012-phase-2-strategy-decisions.md](ADR-0012-phase-2-strategy-decisions.md) | Phase 2 strategy decisions D-P2-1..11 | Accepted |
| [ADR-0013-change-engine-module.md](ADR-0013-change-engine-module.md) | The prototype change engine becomes a module of Part 2 | Accepted |
| [ADR-0014-theming-and-tenant-branding.md](ADR-0014-theming-and-tenant-branding.md) | Theming and tenant branding | Accepted |
| [ADR-0015-country-packs-calendars-locale.md](ADR-0015-country-packs-calendars-locale.md) | Country packs, calendars and locale | Accepted |
| [ADR-0016-engine-invisibility.md](ADR-0016-engine-invisibility.md) | The engine is invisible to customers | Accepted |
| [ADR-0017-operating-rules-two-founders-and-agents.md](ADR-0017-operating-rules-two-founders-and-agents.md) | Operating rules for two founders and their agents | Accepted |
| [ADR-0018-development-environments-and-progress-viewing.md](ADR-0018-development-environments-and-progress-viewing.md) | Development environments and progress viewing | Accepted |
| [ADR-0019-enforcement-layers.md](ADR-0019-enforcement-layers.md) | Enforcement layers for the operating rules | Accepted |
| [ADR-0020-lane-guard.md](ADR-0020-lane-guard.md) | Lane guard | Accepted |
| [ADR-0021-public-repo-and-branch-protection.md](ADR-0021-public-repo-and-branch-protection.md) | Public repository with branch protection | Accepted |
| [ADR-0022-web-stack.md](ADR-0022-web-stack.md) | Web stack for the marketing site and the app | Accepted |
| [ADR-0023-one-github-account-per-founder.md](ADR-0023-one-github-account-per-founder.md) | One personal GitHub account per founder | Accepted |
| [ADR-0024-four-phase-1-markets.md](ADR-0024-four-phase-1-markets.md) | Four phase-1 markets, no fixed launch order | Accepted |
| [ADR-0025-independent-founder-lanes-in-the-plan.md](ADR-0025-independent-founder-lanes-in-the-plan.md) | Independent founder lanes in the plan | Accepted |
| [ADR-0026-phased-delivery-and-market-pack-track.md](ADR-0026-phased-delivery-and-market-pack-track.md) | Phased delivery, phase exits and the market-pack track | Accepted |
| [ADR-0027-human-floor-action-policy-and-agent-authority.md](ADR-0027-human-floor-action-policy-and-agent-authority.md) | Human floor, action-policy table and agent authority | Accepted |
| [ADR-0028-recoverable-journaled-change-apply.md](ADR-0028-recoverable-journaled-change-apply.md) | Recoverable, journaled change apply (not universal rollback) | Accepted |
| [ADR-0029-engine-disclosure-wording-and-saas-only.md](ADR-0029-engine-disclosure-wording-and-saas-only.md) | Engine disclosure wording and SaaS-only delivery | Proposed |
| [ADR-0030-blueprint-to-engine-mapping-contract.md](ADR-0030-blueprint-to-engine-mapping-contract.md) | Blueprint-to-engine mapping contract | Proposed |
| [ADR-0031-rigid-zone-code-authorship.md](ADR-0031-rigid-zone-code-authorship.md) | Who may write rigid-zone code, and what it must pass | Accepted |
| [ADR-0032-approval-is-a-recorded-review.md](ADR-0032-approval-is-a-recorded-review.md) | Approval is a recorded GitHub review | Accepted |
| [ADR-0033-v1-valuation-rounding-and-arabic-review.md](ADR-0033-v1-valuation-rounding-and-arabic-review.md) | v1 stock valuation, rounding and Arabic review defaults | Accepted |
| [ADR-0034-reviewed-level-needs-a-named-reviewer.md](ADR-0034-reviewed-level-needs-a-named-reviewer.md) | A reviewed component names its reviewer | Accepted |
| [ADR-0035-risk-tiered-review.md](ADR-0035-risk-tiered-review.md) | Risk-tiered review and fewer rounds | Accepted |
| [ADR-0036-tool-api-domain-errors.md](ADR-0036-tool-api-domain-errors.md) | Tool API domain error codes and catalog | Accepted |
| [ADR-0037-manifest-risk-class-and-transition-kind.md](ADR-0037-manifest-risk-class-and-transition-kind.md) | Manifest-declared entity risk class and explicit transition kind | Accepted |
| [ADR-0038-secrets-management.md](ADR-0038-secrets-management.md) | Secrets management: one store interface, signing keys stay in the KMS, nothing secret reaches a log, the repo or a model | Proposed |
| [ADR-0039-role-and-permission-mapping.md](ADR-0039-role-and-permission-mapping.md) | Blueprint roles map to adapter-owned engine roles, field levels and record scopes by a fixed table; anything unmapped or unresolved is denied | Proposed |
| [ADR-0040-tenant-provisioning-service.md](ADR-0040-tenant-provisioning-service.md) | Tenant provisioning is a durable, resumable step machine that observes before it acts and never duplicates a site or a secret | Proposed |
| [ADR-0041-durable-adapter-state-on-tenant-database.md](ADR-0041-durable-adapter-state-on-tenant-database.md) | Durable adapter state lives in the tenant database | Proposed |
| [ADR-0042-zatca-phase-2-vendor-core-rebuild-state.md](ADR-0042-zatca-phase-2-vendor-core-rebuild-state.md) | ZATCA Phase 2: vendor the ERPGulf pure core, rebuild state | Proposed |
| [ADR-0043-department-assistants.md](ADR-0043-department-assistants.md) | Department-scoped assistants in the Blueprint (Blueprint 0.4.0) | Proposed |
| [ADR-0044-ag-ui-agent-to-screen-transport.md](ADR-0044-ag-ui-agent-to-screen-transport.md) | AG-UI as the agent-to-screen transport, not an authority | Proposed |
| [ADR-0045-opening-import-transaction-boundary.md](ADR-0045-opening-import-transaction-boundary.md) | Opening import identity and transaction boundary | Proposed |
| [ADR-0046-opening-import-review-boundaries.md](ADR-0046-opening-import-review-boundaries.md) | Opening import review boundaries | Proposed |
| [ADR-0047-mfa-design.md](ADR-0047-mfa-design.md) | MFA design: TOTP now, step-up, recovery, throttling, session binding | Proposed |
| [ADR-0048-agent-authority-propose-not-act.md](ADR-0048-agent-authority-propose-not-act.md) | Agent authority: agents propose, humans and deterministic code decide | Proposed |
| [ADR-0049-human-review-queue.md](ADR-0049-human-review-queue.md) | Human review queue and the team_reviewed gate evidence | Proposed |
| [ADR-0050-build-state-machine.md](ADR-0050-build-state-machine.md) | Build state machine, draft to live, with the human gates | Proposed |
| [ADR-0051-adapter-role-and-state-namespacing.md](ADR-0051-adapter-role-and-state-namespacing.md) | Adapter-owned engine roles and workflow states carry a reserved prefix, collisions are refused, role.upsert writes the mapped grants | Proposed |
| [ADR-0052-isolated-browser-runner-placement.md](ADR-0052-isolated-browser-runner-placement.md) | Isolated browser runner placement (Tier 5 connector) | Proposed |
| [ADR-0057-compiler-and-studio-design-confirmations.md](ADR-0057-compiler-and-studio-design-confirmations.md) | Compiler, token-resolver and Studio design confirmations from open questions | Proposed |
| [ADR-0056-golden-path-mapping-gaps.md](ADR-0056-golden-path-mapping-gaps.md) | Golden-path engine mapping: complete unmapped list, computed fields engine-authoritative | Proposed |
| [ADR-0054-model-call-contract.md](ADR-0054-model-call-contract.md) | Model-call interface contract | Proposed |
| [ADR-0058-design-confirmations-batch-2.md](ADR-0058-design-confirmations-batch-2.md) | Design confirmations batch 2: compiler scope, connector refusals, fonts, Tool API risk | Proposed |
| [ADR-0055-purchasing-engine-mapping.md](ADR-0055-purchasing-engine-mapping.md) | Purchasing and price-list engine mapping (contract 0.2.0) | Proposed |
| [ADR-0059-draft-country-packs-in-sandbox.md](ADR-0059-draft-country-packs-in-sandbox.md) | Draft country packs may run in sandbox and test (synthetic data only); partly supersedes ADR-0034 | Accepted |
| [ADR-0060-role-assignments-in-regional-store.md](ADR-0060-role-assignments-in-regional-store.md) | Role assignments live in a regional store outside the tenant site, under the security conditions of the GOV-066 review; supersedes ADR-0007 item 9 | Accepted |
| [ADR-0062-tool-api-roles-from-assignment-store.md](ADR-0062-tool-api-roles-from-assignment-store.md) | Tool API section 4 step 2 loads the caller's roles from the regional assignment store, fail closed, re-read on approved execution (Tool API 0.3.2) | Accepted |
| [ADR-0063-country-pack-certification-record.md](ADR-0063-country-pack-certification-record.md) | Country pack certification records: market accountant sign-off, one founder, matching manifest and named reviewer (CMP-035, Q-560) | Accepted |
| [ADR-0066-final-name-seshna-and-nuqta-s-mark.md](ADR-0066-final-name-seshna-and-nuqta-s-mark.md) | Final product name Seshna (seshna.com) and the Nuqta S mark with Cairo headings; supersedes the ADR-0001 working-name rule and the logo and heading typeface of ADR-0011 (trademark not cleared) | Accepted |
| [ADR-0069-gateway-live-binding-audit-spool.md](ADR-0069-gateway-live-binding-audit-spool.md) | Gateway live binding: durable audit spool, identity-bound audit records, request and response size caps (PLT-027) | Proposed |
