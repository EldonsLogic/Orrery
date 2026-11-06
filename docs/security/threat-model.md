# Threat model (v0)

Status: draft
Owner: eldon

Method: assets -> actors -> trust boundaries -> threats and mitigations. Revisit at each gate and after any new connector.

## Assets
Tenant business and personal data; tenant ledger and tax records; e-invoice keys (CSID, private keys); tenant credentials/API keys for connectors; Blueprints and component library (our IP); model gateway keys; brand assets; audit logs; control-plane access.

## Actors
Anonymous internet; tenant user (low/high privilege); malicious tenant; compromised tenant account; customer's supplier/buyer (sends documents); our staff/support (insider); third-party processors (cloud, LLM provider); open-source maintainers (supply chain); automated agents (ours).

## Trust boundaries
Internet | web/app | services (discovery, blueprint, operate, gateway, control plane) | engine (per-tenant site) | data stores | LLM providers | connectors and customer tools (untrusted content) | internal console.

## Threats and mitigations
| # | Threat | Boundary | Mitigations |
|---|---|---|---|
| T1 | Prompt injection via customer documents, emails, Odoo records, OCR text | connectors -> LLM | Treat all read content as data; separate instruction and data channels; tool allow-list per mode; no tool call authorised by document text; high-risk actions need human approval; output schema validation; injection tests in evals; log inputs |
| T2 | Chat tricked into acting beyond user's rights | LLM -> tool API | Tool API checks caller role and scope on every call; chat acts with user's own permissions; no ambient admin tokens; deterministic rigid zone (ledger, tax, e-invoicing, payroll, audit) not callable by AI for edits |
| T3 | Tenant escape (cross-tenant read/write) | services/engine | Site-per-tenant; tenant ID bound to every request from identity; per-tenant keys and storage prefix; cross-tenant tests in CI; no shared DB credentials across tenants; semantic layer scoped by tenant |
| T4 | Credential theft or misuse (owner's tool credentials, API keys) | connectors | Prefer read-only scoped keys; never store owner's passwords; browser-session fallback never stores credentials; keys in secret manager, per-tenant, revocable; shown once; revoke after import |
| T5 | Malicious brand/uploaded assets (SVG script, polyglot, malware, zip bomb) | web/app -> storage | [brand-asset-upload-security.md](brand-asset-upload-security.md): type allow-list, content sniffing, size limits, SVG sanitisation, scan, separate origin, safe headers |
| T6 | Supply chain (dependencies, Frappe apps, images, CI actions, third-party apps like ZATCA app) | build | Pin versions; licence and provenance review before adoption; Dependabot; lockfiles; signed images; review of third-party app code before use; minimal CI permissions |
| T7 | Insider and support access to tenant data | internal console | Just-in-time, time-boxed, audited access with tenant notification; no standing production access; separation of duties on certification; background checks (policy TBD) |
| T8 | LLM provider data exposure or retention; cross-border transfer | gateway -> provider | Approved provider list; no-training and zero/low retention terms; regional routing; minimal context and redaction; DPA; legal position UNVERIFIED ([../compliance/data-protection-and-residency.md](../compliance/data-protection-and-residency.md)) |
| T9 | Cost abuse (token flooding, runaway agents, free-tier abuse) | gateway | Per-tenant and per-user budgets and rate limits; hard caps; anomaly alerts; scheduled agent budgets; sign-up abuse controls |
| T10 | Compromised signing keys (ZATCA CSID) | engine | Keys in secret manager/HSM-like store, per tenant, access logged; rotation and revocation runbook |
| T11 | Config change causes outage or wrong tax (bad Blueprint) | blueprint/engine | Validator, DDL plan gate, preview, human review gate, sandbox, simulation, rollback; rigid zone excluded from AI edits |
| T12 | Account takeover of tenant owner | web/app | MFA, OTP rate limits, session management, new-device alerts, step-up for sensitive actions |
| T13 | Phishing/spoofed invoices through documents inbox | documents | Sender verification hints, bank-detail change always requires human approval, flag anomalies |
| T14 | Data leak through logs, errors, analytics | all | Log scrubbing; no personal data in URLs; analytics consent |
| T15 | Regulation drift makes output non-compliant | engine | [../compliance/regulation-watch.md](../compliance/regulation-watch.md) process; effective-dated config |
| T16 | Denial of service | edge | Rate limiting, WAF/CDN, per-tenant quotas |

## Residual risks and open items
Hardware-level isolation not used (shared workers); LLM provider breach cannot be prevented, only minimised; regulatory scope for us (NCA/CST) UNVERIFIED. Review with an independent tester at G3.
