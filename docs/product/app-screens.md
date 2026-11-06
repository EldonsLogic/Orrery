# App screens (post sign-in)

Status: draft
Owner: eldon

Code lives in `web/app` (empty until gate G1+). Roles: O owner, A accountant, S sales, W warehouse, H HR (later), Adm admin (owner or delegated). All screens: light/dark themes, tenant branding, Arabic RTL, loading/empty/error states. The chat acts with the user's permissions; screens are generated from role, function and scope.

## Tenant app screens
| Screen | Purpose | Roles | Key data | Key actions |
|---|---|---|---|---|
| Home / chat | One entry point; modes discover, ask, act, change | All | Conversation, mode, suggestions, pending approvals count | Chat, switch mode, attach files, open linked records |
| Blueprint viewer and approval | See and approve the business model | O, Adm; A read | Entities, workflows, roles, approvals, reports, integrations, compliance profile, branding, version history, diff | Edit by chat/form, approve, compare versions, roll back |
| Connect sources | Bring in existing data | O, Adm, A | Source tiers, status, last read, what was extracted | Upload, connect Odoo, forward address, disconnect |
| Quote and plan | Price and accept | O | Setup fee, plan, AI budget, scope items, uncovered needs | Accept, ask change, download PDF |
| Build progress | Show build state | O, Adm | State, steps, component list, blockers, team notes | Cancel request, ask question |
| Simulation report | Trust before go-live | O, A | Replayed month totals vs source, mismatches, tax totals | Mark expected/wrong, re-run, accept |
| Go-live checklist | Controlled cut-over | O, Adm, A | Checklist, ZATCA onboarding status, backups, users | Complete items, go live |
| Owner dashboard | Cash, sales, dues, stock value, approvals | O | Metrics from the semantic layer | Drill down, ask by chat |
| Accountant dashboard | Close and VAT | A | Open items, ageing, VAT summary, bank, e-invoice status | Post, reconcile, run reports |
| Sales dashboard | Pipeline to invoice | S | Quotes, orders, customer balance, stock | Create quote/order/invoice |
| Warehouse dashboard | Stock operations | W | Receipts due, deliveries, counts, low stock | Receive, issue, count |
| Approval inbox | One place for approvals | O, A, others by rule | Pending items with context, amount, requester, policy | Approve, reject, delegate |
| Reports library and builder | Find or create reports | O, A, S, W (scoped) | Saved reports, schedules | Run, export, schedule, create by chat |
| Notifications | Alerts and tasks | All | Approvals, e-invoice rejections, regulation notices | Open, snooze, set preferences |
| Documents inbox | Supplier invoices, receipts, photos | A, W | Uploaded docs, OCR results, confidence, untrusted-content flag | Confirm fields, create bill/receipt, reject |
| Audit log | Who did what, including AI | O, Adm, A | Event stream entries, actor (person or agent), before/after | Filter, export |
| Settings > Company | Legal names (Arabic and English), CR, VAT, addresses, fiscal year | O, Adm | Company profile | Edit (audited) |
| Settings > Users and roles | Access | Adm | Users, roles, scopes, MFA state | Invite, assign, suspend |
| Settings > Billing | Plan, usage, invoices | O, Adm | Plan, entitlements, AI-action usage, invoices | Change plan, buy pack |
| Settings > Language | Language, calendar display | All (own) | Language, Hijri display option | Change |
| Settings > Integrations | Connectors and keys | Adm | Connected tools, status | Connect, revoke |
| Settings > Branding | Tenant look | O, Adm | Logo variants, name, colour, favicon, login page, preview | Upload, preview, apply ([theming-and-tenant-branding.md](theming-and-tenant-branding.md)) |
| Settings > Data export | Leave with your data | O | Export history | Request export, request deletion |
| Help | Support | All | Articles, contact, status | Search, contact |

## Internal team console (separate app, internal identity, never customer-facing)
| Screen | Purpose | Roles | Key data | Key actions |
|---|---|---|---|---|
| Review queue | Human gate | Reviewer | Blueprint, diff, risks, compliance profile, simulation | Approve, edit, reject with reasons |
| Component factory | Gap -> request -> certify | Engineer | Component requests, spec, tests, certification level | Review, certify, publish to library |
| Tenant ops | Lifecycle and health | Ops | Tenants by state, version, usage, incidents | Suspend, restore, migrate (audited) |
| Support access | Just-in-time access | Support | Requests, approvals, expiry | Request/approve access (tenant notified, logged) |
| Model and cost | Gateway view | Ops | Spend per tenant, budgets, errors | Adjust budgets, switch route |

## Role-view matrix (v = view, a = act, ap = approve, x = none)
| Area | Owner | Accountant | Sales | Warehouse | HR (later) | Admin |
|---|---|---|---|---|---|---|
| Blueprint | v, ap | v | x | x | x | v, a |
| Sales docs | v, ap | v, a | v, a (own scope) | v | x | v |
| Purchasing | v, ap | v, a | x | v, a | x | v |
| Inventory | v | v | v | v, a | x | v |
| Ledger and VAT | v | v, a, ap | x | x | x | v |
| E-invoice status | v | v, a | v (own) | x | x | v |
| Payroll (later) | v, ap | v | x | x | v, a | v |
| Reports | v | v, a | v (scoped) | v (scoped) | v (scoped) | v |
| Users and roles | v | x | x | x | x | v, a |
| Branding | v, a | x | x | x | x | v, a |
| Billing | v, a | v | x | x | x | v, a |
| Audit log | v | v | x | x | x | v |
Scopes (branch, warehouse, customer group) narrow every row. This is a default; roles come from the Blueprint.

## States in the brand voice
Rule: say what is true, what is missing, what happens next ([../brand/06-voice-tone.md](../brand/06-voice-tone.md)). Arabic equivalents are written by a native speaker (unreviewed).
| State | EN example |
|---|---|
| Empty (documents inbox) | No documents yet. Forward a supplier invoice to your inbox address or upload one. |
| Empty (approvals) | Nothing waiting for you. |
| Loading (simulation) | Replaying March: 412 of 1,180 transactions checked. |
| Error (e-invoice) | Invoice INV-0418 was rejected: the buyer's VAT number has 14 digits, not 15. Fix it and resend. |
| Denied | You can't approve this. Payments over SAR 50,000 need the owner. Request approval? |
| Budget reached | This month's AI actions are used up. Existing reports still work. Add a pack or wait for the reset on the 1st. |
| Offline / unavailable | Can't reach the server. Your last changes are saved. We'll retry. |
Numbers in examples are illustrative.

## Settings > Company calendar and week (added)
| Item | Detail |
|---|---|
| Purpose | Per-company calendars, work-week and time; defaults come from the country chosen at sign-up (KSA, UAE, Egypt); actual defaults are research needed ([../compliance/country-matrix.md](../compliance/country-matrix.md)) |
| Roles | Owner and admin only; others view effects |
| Settings | Week start day; weekend days; working days and hours, including reduced Ramadan hours (date range, hours); primary and secondary calendar (Gregorian, Hijri, Coptic where relevant); fiscal year start; holiday calendar with company overrides (add, remove, move; Hijri holidays may shift with moon sighting); time zone; number system (Western or Eastern Arabic digits) |
| Key actions | Edit, preview (sample dates, a week view, a sample invoice and report), apply, reset to country defaults |
| Audit | Every change versioned and logged with who, before and after; effective-dated so past documents do not change |
| Specs | [../architecture/country-packs.md](../architecture/country-packs.md), [../architecture/calendars-and-locale.md](../architecture/calendars-and-locale.md) (written by another agent) |

## Date pickers
Every date picker shows the primary calendar and can show the secondary beside it, and accepts input in either; conversion is display only (stored value is Gregorian); respects the company week start, weekend and holidays; works in RTL and with both number systems; keyboard and screen-reader accessible. Hijri/Gregorian conversion rules: see calendars-and-locale.md.
