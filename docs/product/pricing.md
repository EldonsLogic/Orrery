# Pricing and entitlements

Status: draft
Owner: eldon

Prices are hypotheses owned by [../strategy/07-pricing.md](../strategy/07-pricing.md) (setup SAR 20-60K, subscription per company with unlimited users SAR 2-5K/month, AI-actions budget, annual prepay discount). Do not duplicate numbers here; this page defines how the platform enforces them.

## Free-first with entitlements built in
At launch everything is unlocked and free for approved tenants, but every capability is already tied to a plan entitlement and every AI action is metered, so gating can be switched on by configuration.

## Entitlement design
| Concept | Design |
|---|---|
| Plan | A named bundle of entitlements (e.g. Core, Operate, Scale from strategy/07) assigned per tenant, effective-dated |
| Entitlement | Key plus value: boolean (feature on/off), limit (number), or tier (level). Evaluated server-side only |
| Examples | `module.hr_payroll` (bool), `agents.scheduled.max` (limit), `ai.actions.monthly` (limit), `branding.remove_powered_by` (bool), `branding.custom_domain` (bool, later), `support.priority` (tier), `entities.max` (limit), `data.export.full` (always true) |
| Free-first mode | A global flag grants all entitlements to tenants in the program; usage still recorded |
| Overrides | Per-tenant overrides by the internal team, audited, with expiry |
| Never gated | Data export, security features (MFA), legal/compliance fields on documents |

## Metering of AI actions
| Item | Rule |
|---|---|
| Unit | "AI action" = one completed user-visible task (e.g. answer, draft, report run, applied change); definition and weights set in the gateway and published to customers |
| Customers see | AI actions used / included. Never tokens |
| Internal | Tokens, model, cost per action recorded in the event stream for margin tracking |
| Budget | Hard monthly cap per tenant with alerts at set thresholds; scheduled agents have their own budgets; overage via prepaid packs (strategy/07: cost plus about 30%, hypothesis) |
| Abuse | Rate limits per user and tenant; anomaly alert on cost spikes ([../security/threat-model.md](../security/threat-model.md)) |
| Reset | Monthly; behaviour on exhaustion: existing reports and reads keep working, new AI actions pause with a clear message |

## "Powered by" removal as an entitlement
Default: the platform mark appears in the app chrome and on tenant-facing login. `branding.remove_powered_by` removes it from the app chrome only; the legal footer and compliance text stay. Which plan includes it: open (decide with pricing tests). See [theming-and-tenant-branding.md](theming-and-tenant-branding.md).

## Billing outline
Per-company subscription in SAR (AED for UAE: open), setup fee in milestones (blueprint approved, simulation passed, go-live), UAE e-invoicing provider fees as a separate line. Payment methods and VAT on our own invoices: research needed (we must issue compliant invoices ourselves; entity position UNVERIFIED, [../legal/checklist.md](../legal/checklist.md)).

## Tests to run
Listed in [../strategy/07-pricing.md](../strategy/07-pricing.md) section "Tests to run". Add: does removing "Powered by" have willingness to pay.
