# Static analysis for factory-built components

Plan ID: SEC-010. Status: draft. Owner: eldon. Approved by: pending (review with a different model). Code: `services/blueprint/factory/analysis/` (kept in the Blueprint lane, which owns the factory; no separate security service exists yet). Builds on BPL-015 (logical sandbox) and the risk tiers of [ADR-0035](../decisions/ADR-0035-risk-tiered-review.md).

## Decision
Every file of a factory-built component is analysed statically, before any candidate command runs. One HIGH finding keeps the component at `draft`, skips its tests and blocks `tested`. The analyser is deterministic code, not a model: the same files always give the same report, so a reviewer can rerun it.

## What it catches (threat T: a model-written component exfiltrates, escapes or hides)
Network, filesystem escape, subprocess, `eval` and `exec`, dynamic import, secrets and environment reads, engine-internal imports, undeclared capabilities against the manifest (model SDKs, components outside `requires`), obfuscation, interpreter introspection, unsafe deserialisation, hard-coded credentials, and unreadable or compiled files (fail closed). Embedded scripts in JSON are scanned as Python. Codes `SA-001` to `SA-015`: see the analysis README.

## Posture after review: allow-list (PR #172 Tier 3 review)
The first cut was a deny-list; the review showed 30 of 36 evasions passing it (a UTF-7 coding line hiding the whole file, aliased builtins, `__self__` and `__dict__` walks, star imports, whole `os` families, stdlib modules that re-export `os`, pytest config and doctest files). The analyser now allows a fixed safe surface and refuses the rest. The full list is in the analysis README; in short:
- Imports: a fixed list of safe standard modules, `pytest`, the component's own package, its `requires` components and its own files. Every other import is HIGH, including model SDKs and any third-party module. `os` only for `os.path` helpers.
- Dangerous builtins (`eval`, `exec`, `compile`, `__import__`, `open`, `getattr`, `setattr`, `delattr`, `globals`, `locals`, `vars`, `breakpoint`, `input`, `help`): any reference other than a checked direct call is HIGH, and so is rebinding them by assignment, import or parameter. Non-data dunders, modules used as values and star imports are HIGH.
- Source is parsed from raw bytes and any coding line other than utf-8 is HIGH. Test-runner and interpreter configuration files, doctest prompts in text files and non-Python embedded scripts are HIGH. The test runner isolates pytest from anything the component ships (empty config, no conftest, no addopts, no doctest plugin, no plugin auto-load).
- SA-007 (platform internals, now also `factory`, `registry`, `services`, `apps` and direct database clients) applies to every factory candidate. There is no exemption read from the manifest: the manifest is candidate-controlled, so a candidate could simply declare itself a library component. Library and upstream components never enter the factory, so the exemption lives at the call site, not in data (answers Q-181; an ADR is still to be written).
- A credential-like name (`api_key`, `dbPassword`) is HIGH only with a key-like value, so `author` or `tokenizer` no longer block.

The evasion corpus (`services/blueprint/tests/factory/test_analysis_evasions.py`) holds every case from the review; each must give a HIGH finding.

## What it does not do
Static analysis is defence in depth. It is not a security boundary: Python can still be written to evade any rule set. The real boundary is the OS-level sandbox (INF-014) plus a named reviewer (ADR-0034), with the Tool API policy behind them. A component that passes static analysis can still never reach above `tested` here. Known deferred gaps: computed `pathlib` paths (review M2), computed format strings, `uuid.getnode` running a fixed system command, and pytest `monkeypatch` string targets.

## Fail-closed choices
Unparseable, binary or non-Python script files and analyser crashes are HIGH. MEDIUM and LOW are warnings so a human reviewer sees them; they never block (decision recorded here, as the review asked). An embedded value under `code` that does not parse is LOW, because that key usually holds an identifier. The manifest has no permissions block today; "declared" means `requires`, `dataHandling.sendsDataToModels` and the component's own files (open question Q-180).
