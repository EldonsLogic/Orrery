# Static analysis for factory-built components

Plan ID: SEC-010. Status: draft. Owner: eldon. Approved by: pending (review with a different model). Code: `services/blueprint/factory/analysis/` (kept in the Blueprint lane, which owns the factory; no separate security service exists yet). Builds on BPL-015 (logical sandbox) and the risk tiers of [ADR-0035](../decisions/ADR-0035-risk-tiered-review.md).

## Decision
Every file of a factory-built component is analysed statically, before any candidate command runs. One HIGH finding keeps the component at `draft`, skips its tests and blocks `tested`. The analyser is deterministic code, not a model: the same files always give the same report, so a reviewer can rerun it.

## What it catches (threat T: a model-written component exfiltrates, escapes or hides)
Network, filesystem escape, subprocess, `eval` and `exec`, dynamic import, secrets and environment reads, engine-internal imports, undeclared capabilities against the manifest (model SDKs, components outside `requires`), obfuscation, interpreter introspection, unsafe deserialisation, hard-coded credentials, and unreadable or compiled files (fail closed). Embedded scripts in JSON are scanned as Python. Codes `SA-001` to `SA-015`: see the analysis README.

## What it does not do
It is not a security boundary: Python can be written to evade a pattern table. It does not replace the OS-level sandbox (INF-014), the named reviewer (ADR-0034) or the Tool API policy. Passing it proves only that no known pattern fired, so `tested` stays a low rung and nothing above it is granted here.

## Fail-closed choices
Unparseable, binary or non-Python script files and analyser crashes are HIGH. MEDIUM and LOW are warnings so a human reviewer sees them. The manifest has no permissions block today; "declared" means `requires`, `dataHandling.sendsDataToModels` and the component's own files (open question Q-180).
