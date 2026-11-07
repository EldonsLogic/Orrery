# ADR-0025: Independent founder lanes in the plan

Status: Accepted
Owner: eldon
Approved by: Eldon (founder instruction, 2026-11-07)

## Context
Two founders and their agents work in parallel. Lanes by file path (ADR-0020) stop edit collisions, but 210 plan rows had no owner and a few rows waited on the other founder's work inside the same gate (the compiler needed the engine implementation, and apply needed the compiler). Either founder could be blocked or collide by picking an unowned row.

## Decision
- Every open plan row has exactly one owner, eldon or partner, matching the lane of the paths it touches.
- Inside a gate the two lanes are independent: a row may depend on the other founder's row only if that row is done or in an earlier gate. `scripts/check_plan_independence.py` enforces this in the docs gate, CI, pre-push and the finish gate.
- Cross-lane needs are met by interface rows scheduled earlier: a contract plus a fake or fixture and a conformance test (BPL-025 engine adapter contract and fake, BPL-026 compiled-artifact contract). Each side builds against the interface; an integration row at a later gate joins them (BPL-027).
- Lane changes that follow from this: `connectors/` (discovery connectors) and `services/control-plane/` go to Eldon; `services/gateway/` (engine-facing API gateway) goes to the partner. Everything else stays as in ADR-0020.
- Rebalancing is allowed by changing an Owner in a PR if the check still passes. Eldon holds more rows than the partner at G2 (product, operate, web, platform services); revisit the split before G2 starts.

## Alternatives rejected
- Leave rows unassigned until needed: invites collisions and silent blocking.
- Strict path ownership with no gate rule: still lets the compiler wait on the engine in the same gate.

## Consequences
- Work on both sides can start at the same time within a gate. Integration is a planned row, not a surprise.
- The partner's agent must read the interface contracts (BPL-025, BPL-026) before building the adapter and apply.
- A new row that breaks independence fails CI until its gate or owner is fixed or an interface row is added.

## Supersedes
none (extends ADR-0020)
