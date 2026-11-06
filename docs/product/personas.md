# Personas

Status: draft
Owner: eldon

All personas are hypotheses until the 25-interview plan ([../gtm/README.md](../gtm/README.md)) validates them. Evidence of how owner-led firms buy is thin (UNVERIFIED, [../research/02-market-and-customer.md](../research/02-market-and-customer.md) section 2).

| Persona | Who | Goals | Pains | Uses the platform to | Default role view | Success signal |
|---|---|---|---|---|---|---|
| Owner / GM | Founder-operator of a 10-100 staff company; decides and approves | See cash, sales, stock and dues in one place; stay ZATCA/VAT compliant without learning accounting; stop depending on one partner | Long ERP projects, partner lock-in, opaque costs, WhatsApp chaos | Describe the business, approve the Blueprint, ask questions, approve payments and discounts | Owner dashboard, approval inbox | Asks "how much do customers owe me?" and trusts the answer |
| Accountant / finance | In-house finance manager or external accountant/VAT consultant (likely shortlist influencer, UNVERIFIED) | Correct books, VAT returns data, clean month-end; no double entry | Re-keying, reconciliation, compliance fear, tool changes forced on them | Review chart of accounts and tax setup, post and approve entries, run VAT and ageing reports | Accountant dashboard, reports library | Month closes without spreadsheets; veto not triggered |
| Sales | Salespeople, sales manager | Quote and invoice fast, see customer credit and stock | Waiting for finance, wrong prices, no stock visibility | Create quotes/orders by chat or form, check customer balance | Sales dashboard | Invoice issued in minutes, no rework |
| Warehouse / stock | Storekeeper, purchasing clerk | Receive, issue, count stock accurately | Paper notes, mismatched stock, supplier chasing | Record receipts and deliveries, scan documents, stock counts | Warehouse dashboard | Stock on screen equals shelf |
| HR (later) | HR officer or owner's assistant | Staff records, leave, payroll file for WPS | Manual payroll, GOSI/WPS formats | Payroll runs, WPS/SIF export (later release) | HR view (later) | Payroll file accepted by the bank |
| Our team / reviewer | Founders and engineers acting as reviewers, component-factory engineers, support | Review each Blueprint before build, certify new components, support tenants safely | Hidden risks in generated config, unclear gaps | Review queue, component factory, tenant ops, audited just-in-time access | Internal console (separate app) | Review time per Blueprint falls; no unreviewed build goes live |

## Role-view rule
Anyone in the company can chat. The chat acts with the user's own permissions, and each person gets screens and tools generated from role, function and scope (ADR-0004 in [../decisions/](../decisions/)). Matrix: [app-screens.md](app-screens.md).

## Language
Owners may chat in Arabic (Gulf-friendly Modern Standard Arabic, per [../brand/06-voice-tone.md](../brand/06-voice-tone.md)) or English; staff may differ from the owner. Language is a per-user setting.
