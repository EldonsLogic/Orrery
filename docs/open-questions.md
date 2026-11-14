# Open questions

Status: accepted
Owner: eldon

The canonical list from Phase 1-2 is [strategy/open-questions.md](strategy/open-questions.md). Keep adding there for strategy items. This file adds platform and build questions raised during foundation work. Answered items move into an ADR and are struck here with the ADR number.

| # | Question | Owner | Needed by | Related |
|---|---|---|---|---|
| Q-1 | RESOLVED 2026-11-07 (ADR-0007 accepted: central identity with per-tenant roles). Was: identity model, one central identity with per-tenant roles, or identity per tenant? | eldon | G0 | PLT-002 |
| Q-2 | Where does the isolated read-only browser runner live (our infrastructure, owner's device, third-party)? Affects credentials, egress and PDPL | unassigned | G3 | INF-009, SEC-015 |
| Q-3 | Final GitHub repo name and organisation name (working name is not cleared) | eldon | G0 | GOV-002, ADR-0001 |
| Q-4 | Arabic spelling and transliteration of the product name for search and brand | eldon | G1 | BRD-003 |
| Q-5 | Tenant branding limits: which plan may remove "Powered by", how many colours, custom fonts allowed (default no) | eldon | G2 | PLT-018, ADR-0014 |
| Q-6 | Which Frappe/ERPNext/HRMS version set to pin and when to move? ERP-001 proposes v15.126.0, v15.124.5 and v15.64.8 respectively; compatibility on a dedicated bench is UNVERIFIED. Update 2026-11-14: the set builds cleanly and runs on a local synthetic bench (see the ERP-001 log of that date); behaviour under real workloads and the move policy (ERP-004) remain open. | partner | G1 | ERP-001, ERP-004 |
| Q-7 | Licence for our own repo and for contracts/ if we ever publish them | eldon | G0 | LEG-002 |
| Q-8 | Which accounting standard and chart of accounts default for KSA, UAE, Egypt and Qatar templates | unassigned | G1 | CMP-006 |
| Q-9 | Which cloud or hosting provider can keep tenant data in-country with acceptable cost | unassigned | G1 | INF-001 |
| Q-10 | Do first clients accept data going to a foreign-region model endpoint, or must we use in-region only | eldon | G2 | LEG-012, PLT-010 |
| Q-11 | Egypt regulations (e-invoicing, VAT, data protection, payroll) and whether Coptic calendar or Egypt DST matter for the product: all UNVERIFIED | unassigned | G3 | CMP-027, ADR-0015 |
| Q-12 | Which Hijri conversion library (Umm al-Qura), and how moon-sighting overrides are authored and audited | unassigned | G1 | CMP-022, ADR-0015 |
| Q-13 | RESOLVED 2026-11-07 (ADR-0021: repo made public, protection enabled). Was: GitHub refuses branch protection on a private repo without a paid plan (HTTP 403). Upgrade to GitHub Pro or Team so `main` takes only reviewed PRs with passing checks, or accept discipline-only enforcement for now? | eldon | G0 | GOV-008 |
| Q-14 | Where does the central identity store live with four markets (KSA, UAE, Egypt, Qatar)? One store per country with cross-country linking, or one store with legal sign-off for cross-border personal data (names, contacts, MFA factors, login logs)? Also: may staff abroad access in-country tenant data? | eldon | G1 | PLT-005, ADR-0007, LEG-003 |
| Q-15 | Pin the dev Redis image to 7.2.x or switch to Valkey? ERP-001 proposes `redis:7.2.7-alpine`; the upstream licence reading and bench verification remain UNVERIFIED pending review. Partner changes infra/dev/docker; counsel confirms the licence reading. | partner | G1 | LEG-004, ERP-001 |
| Q-16 | How should the golden path and mapping specify order submission, invoice cancellation, source-row links and operation-scoped idempotency? Proposed: make each explicit in the contract and verify behavior on the bench. The packaged-source review is not a live conformance proof. | eldon | G1 | BPL-028, BPL-029, ERP-021, ERP-022 |
| Q-21 | Inventory valuation method default: the pinned bench defaults `Stock Settings.valuation_method` to `FIFO`, whereas `docs/specs/golden-path-trading-sale.md` assumes Moving Average. Should tenant provisioning set `Moving Average` or should the golden path use `FIFO`? | partner | G1 | ERP-005, ERP-014, ERP-022, BPL-028 |
| Q-22 | Rounding method default: the pinned bench defaults `System Settings.rounding_method` to `Banker's Rounding (legacy)`, whereas `BPL-029` (`contracts/examples/engine-mapping-golden-path.json`) specifies `half_up` (`Commercial Rounding`). Which rounding method should v1 tenant provisioning enforce? | partner | G1 | ERP-005, ERP-014, BPL-029 |
| Q-23 | Immutable ledger: `Accounts Settings.enable_immutable_ledger` defaults to `0` on the pinned bench. Confirm setting it to `1` for v1 tenants and verify cancellation and credit-note behaviour in `ERP-021` / `ERP-022`. | partner | G1 | ERP-005, ERP-014, ERP-021 |
| Q-24 | Optional trading doctypes (`Batch` / `Serial and Batch Bundle`, `Landed Cost Voucher`, `Request for Quotation` / `Supplier Quotation`): confirm keeping them hidden by default in v1 and enabling only via `ERP-011` components versus including them in base G2 scope. | partner | G2 | ERP-005, ERP-011 |
| Q-25 | MariaDB 10.6 reached Community EOL on 2026-07-06 (`10.6.28` is final; no further community security or bug fixes). Should we upgrade `infra/dev/docker` and target `INF-005` on MariaDB `11.8` LTS or `10.11` LTS, and gate that compatibility test before G2? | partner | G1 | ERP-001, ERP-004, INF-005 |
| Q-26 | Should we consolidate duplicated version pins across `Dockerfile`, `docker-compose.dev.yml`, and `verify_dev_bench.py` into one machine-readable manifest, and extend `verify_dev_bench.py` to check MariaDB, Python, Node, and `frappe`/`erpnext` commits? | partner | G1 | ERP-001, ERP-004 |
| Q-27 | Do both founders ratify the proposed gate-based security exposure rules (CRITICAL/exploited blocks provisioning and deploys; HIGH blocks staging-to-production promotion) and what trigger rule governs starting the Frappe `v15` (planned EOL end of 2027) to `v16` migration? | partner | G2 | ERP-004, SEC-007, INF-006 |
