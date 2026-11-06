# Frappe build guide (for whoever builds the first version)

Status: working guidance, 2026-11-04. Background: `docs/strategy/04-architecture-and-seed.md`, `docs/research/04-open-source.md`. Nothing here is final; the first build is a test of whether Frappe is the right engine.

## The idea in one paragraph
An owner chats in Arabic or English; an AI interviews them and produces a **Blueprint** (structured description of their business). The Blueprint is compiled into configuration on top of Frappe + ERPNext, using a library of reusable components. The AI configures; it never writes accounting logic and never posts to the ledger without human approval.

## What we are testing with the first build
1. Can a hand-written Blueprint for a small trading company be applied to a fresh Frappe site automatically (custom fields, workflows, roles, print formats), and rolled back?
2. Can we get a compliant KSA invoice (ZATCA) out of it, tested against ZATCA's sandbox?
3. Does an Arabic/bilingual invoice PDF with QR and Hijri date look right?
4. How long does it take to create a new tenant (a new site), and how many fit on one server?
Write down what breaks. That is the result.

## Rules
1. **Configuration, not code.** Customisations go in the app's fixtures/Custom Fields/Workflows/Print Formats, generated from the Blueprint. No per-client code, no editing ERPNext core files. If something needs code, build it as a reusable component.
2. **Keep our own code in our own Frappe app(s)** (e.g. `ourapp_core`), separate from ERPNext. Never modify the `erpnext` or `hrms` source.
3. **The AI layer is a separate service**, not inside the Frappe process. It talks to Frappe only through its REST API/whitelisted methods, using a limited-permission user per tenant, so permissions and audit logs always apply.
4. **Rigid zone:** ledger posting, tax, e-invoicing, payroll maths, audit trail. The AI never edits these.
5. **Arabic first.** All user-facing text goes through Frappe's translation system; nothing hard-coded in English. Test every screen in RTL.
6. **One site per tenant** (Frappe's normal model). Keep tenant creation scripted from day one.

## Licences: do and don't
| Item | Licence | Rule |
|---|---|---|
| Frappe Framework | MIT | Free to use and build on. |
| ERPNext, HRMS | GPL-3 | Fine to run as a hosted service. **Never give the code or an installable copy to a customer** (on-premise or hybrid) without checking with us first. Do not copy their code into our proprietary service. |
| `ERPGulf/zatca_erpgulf` | MIT | Use this for ZATCA. |
| `lavaloon-eg/ksa_compliance` | AGPL-3 | **Do not use.** AGPL forces us to publish our changes. |
| Name | | Do not call anything "ERPNext-something": the trademark policy forbids it in product names, domains and ads. |
| Open Mercato, Twenty, NocoBase, n8n, NocoDB | various | Not used. NocoBase and n8n/NocoDB licences forbid our business model. |

## Versions
Research found Frappe at v16 but the latest ERPNext and HRMS releases at v15. **Pin one consistent, supported set (probably v15 for all three), write it down in the repo, and do not upgrade without telling the team.** Frappe's newer agent/MCP features are only on the development branch; do not depend on them.

## Working with AI coding tools
- Read `AGENTS.md` and `docs/HANDOFF.md` before each session; update HANDOFF at the end.
- Frappe's own repo has an `AGENTS.md` and `skills/` folder for coding agents; use them as reference.
- Commit small, no secrets, no real customer data (use fake sample data).
- Log any decision (a version pin, a library choice) in `docs/strategy/decisions.md`.

## Out of scope for now
Payroll for KSA, UAE and Egypt (HRMS Arabic is only 33% translated and GOSI/WPS were not found in it), UAE e-invoicing (needs an accredited provider partner), the chat UI, real customer data, anything for production.

## Questions to answer in writing at the end
Did the Blueprint apply cleanly? Did the ZATCA sandbox accept our invoices? What was painful about Frappe? How long does a new tenant take? Would you pick Frappe again?
