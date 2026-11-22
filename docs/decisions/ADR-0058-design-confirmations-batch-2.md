# ADR-0058: Design confirmations, batch 2 (compiler scope, connectors, fonts, Tool API risk)

Status: Proposed
Owner: eldon
Approved by: pending (partner review)

## Context
ADR-0057 (Proposed, PR #253, not yet merged) proposes answers to the first batch of "confirm" rows in [docs/open-questions.md](../open-questions.md); this ADR does not depend on its content, but should merge after #253 because both add to `docs/decisions/INDEX.md`. A second pass over the open Eldon-owned rows found 21 candidates. Each was re-read against the current row and the cited code end to end; a row is kept here only when the code (or an accepted ADR or existing plan row) truly answers it. Rows that need a founder business, legal or tax decision, partner work, a contract schema change, or that rest on thin evidence are left open (listed below). Everything decided here is in Eldon's lane or in an existing row; no obligation is added to the partner's lane.

## Decision
"Keep" means the built behaviour is the answer. "Decided, pending" means the answer is fixed here but the work does not exist yet; the row stays open until the named plan row lands. File and line references are on main at the time of writing.

### Compiler and Studio
| Q | Decision | Evidence (file:line) |
|---|---|---|
| Q-61 | Decided, pending BPL-039: the BPL-004 compiler stays initial-build only; incremental compile (base to target with an embedded inverse) is its own row, BPL-039. | `compile_blueprint` emits only the initial build, `base` and `diffHash` null (`services/blueprint/compiler/core.py:20-22`, `:62-63`; `services/blueprint/compiler/__init__.py:40-41`). The artifact schema already carries `inverse` (`contracts/compiled-artifact.schema.json:72`, base and inverse rules `:96-98`) and `reversible` (`:165`), so no contract change is expected for BPL-039; if one is needed it gets its own ADR (contracts/README.md rule 2). BPL-039 is a placeholder and is split into smaller rows when picked. |
| Q-76 | Decided, pending BPL-039: keep the Studio's refusal plus simulated compensation. It is the correct result for an initial build, which the adapter never rolls back (the sandbox is destroyed); Studio shows a real rollback once BPL-039 emits incremental artifacts. | `contracts/engine-adapter.md:142` (5.7: "Rolling back an initial build is not an adapter operation"), `:365` (ADP-C-053); Studio calls the real rollback and reports the refusal (`services/studio/session.py:325-339`, `services/studio/__init__.py:10-14`). |

### Discovery connectors
| Q | Decision | Evidence (file:line) |
|---|---|---|
| Q-90 | Decided, pending INF-014 (existing partner row, unchanged): the runner is the in-process contract only, not an isolation boundary; real parsers run in an OS-level sandbox. Until then only reviewed first-party connectors may be registered: this is a rule stated in a comment (`model.py:12-13`), not enforced in code (`Registry.register`, `model.py:156-160`, checks declarations only). | `services/discovery/connectors/model.py:8-14` (`SANDBOX = "logical"`, no network or file isolation); the connector runs in the caller's process (`services/discovery/connectors/runner.py:292-297`); INF-014 already states the requirement (`docs/PLAN.md:231`). |
| Q-109 | Keep: the runner reports any extract or normalise fault as `CON-010` plus the exception class name; the exception message, which can hold document-derived text, never crosses the boundary. The class name is chosen by the connector and is not validated; it is a static identifier fixed in reviewed code, so this is safe only under the first-party connector rule (Q-90). Each connector's class name carries its code by convention; the runner adds no separate code field. | `services/discovery/connectors/runner.py:292-297`, `:307-312`; convention stated in all four connectors (`connectors/tabular/errors.py:1-2`, `odoo/errors.py:1-3`, `intake/errors.py:1-2`, `forwarding/errors.py:1-3`); the test `services/discovery/tests/connectors/test_connector_framework.py:112-118` proves the message does not leak (it says nothing about the class name). |
| Q-112 | Keep the `ODO-` prefix. | Same pattern as `TAB-`, `INT-` and `FWD-` (`services/discovery/connectors/odoo/errors.py:6-16`, `tabular/errors.py:5-6`, `intake/errors.py:5-6`, `forwarding/errors.py:6-7`). |

### Brand
| Q | Decision | Evidence (file:line) |
|---|---|---|
| Q-119 | Decided, pending WEB-028: fonts are self-hosted subset WOFF2 files (no runtime font CDN). Today no font files are bundled, so the web app falls back to system fonts, and the Studio (a local dev tool) still loads both fonts from Google Fonts at runtime and allows it in its CSP. WEB-028 adds the files and `@font-face` and removes the Studio's CDN link and CSP allowance; it follows BRD-011, which only verifies the licences. | Self-hosting already decided in `docs/decisions/ADR-0022-web-stack.md:23` (Accepted); loading rules and "no font files are bundled" in `docs/brand/fonts/README.md:3` and "Loading in the app"; fallbacks in `docs/brand/tokens/tokens.css:11-12`; Studio CDN `services/studio/static/index.html:7-8`, CSP `services/studio/server.py:20-21`; BRD-011 scope `docs/PLAN.md:242`. |

### Tool API
| Q | Decision | Evidence (file:line) |
|---|---|---|
| Q-139 | Decided, pending SEC-023: keep contact-detail changes (email, phone, notify-to, webhook) as their own R4 tool, not agent-creatable; the action policy table should name them next to bank-detail changes. Stricter than the table, fail closed. | The contract already states it: `contracts/tool-api.md:185` (contact-detail tools are R4 and never agent-creatable). Code: `services/operate/toolapi/policy.py:68-72` (R4 for `update_contact_details`), `:91` (`MAX_AGENT_RISK = "R3"`); the sensitive tools are built at `services/operate/toolapi/generate.py:341-344` and gated by `agent_ok` at `:240-242`; the model never chooses where data goes (`docs/security/prompt-injection-defence.md:197-198`); the table's R4 row names only bank details (`docs/security/action-policy-table.md:59`), and `docs/security/prompt-injection-defence.md:198` names only bank detail and payment address; SEC-023 aligns both. |

Left open (not decided here):
- Q-53, Q-77: making `change_engine` the canonical adapter id would oblige the real adapter (apps/engine, BPL-012) to report that `adapterId` (contract 4.3); needs partner agreement and closes contract 16.12.
- Q-87: who may migrate a frozen revision and whether approvals reset is approval authority; the proposed "back to draft" also conflicts with the framework, which refuses any step that changes `buildState` (`services/blueprint/migrate/core.py:20`, `:203-205`).
- Q-91: who may set `include_hidden` decides what untrusted hidden text reaches the model (security); no caller sets it yet (`services/discovery/connectors/model.py:109`).
- Q-97: CSP nonce or hash is a security decision with no serving code to point at.
- Q-98, Q-120: thin evidence; Q-120 is also a tooling dependency choice.
- Q-116: the row asks for founder confirmation of the caps.
- Q-133: per-locale enum labels change `contracts/tool-api-error-catalog.json` (`:163`, `:212`) and need Arabic review.
- Q-146: the premise is weaker than stated: the picker emits Gregorian ISO converted in the browser (`web/app/src/ui/dateLogic.ts:1`, `:147-148`), so it never hands a Hijri year to the intake's `hijridate` tables; the range choice and the jsdom dependency stay open.
- Q-147, Q-148: identity and session security (MFA scope, step-up, token lifetimes).
- Q-179: the batch write and Excel path depend on the gateway (PLT-009, partner) and a library choice.
- Q-264: multi-part; the limits are placeholders and the agent stream wiring depends on OPR-020.

## Alternatives rejected
- Accept every research verdict: the research was grep-only, and several premises did not hold on reading the code (Q-87, Q-109, Q-146).
- Add a connector refusal code field to the runner output (Q-109): one more connector-set value crossing the boundary for a gain the class name already gives.
- Mark the pending rows resolved: the work does not exist yet.

## Consequences
- Of 21 candidates, 2 are RESOLVED (Q-109, Q-112), 5 are DECIDED and stay open until their row lands (Q-61, Q-76, Q-90, Q-119, Q-139), and 14 stay open.
- Merge after PR #253 (ADR-0057); the second of the two needs main merged in for `docs/decisions/INDEX.md` (no force-push).
- BPL-039 (todo, eldon): incremental compile with an embedded inverse; Studio uses it to show a real rollback (Q-61, Q-76). Split when picked so each PR stays near 400 lines.
- WEB-028 (todo, eldon, after BRD-011): self-host the fonts in the web app and remove the Studio's runtime Google Fonts link and CSP allowance (Q-119).
- SEC-023 (todo, eldon): name contact-detail changes in the R4 row of `docs/security/action-policy-table.md` and in `docs/security/prompt-injection-defence.md` 5.1 (Q-139).
- Partner review is needed before this ADR is Accepted.

## Supersedes
None.
