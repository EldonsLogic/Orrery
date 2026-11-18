# Static analysis for factory-built components (SEC-010)

Deterministic, standard-library-only analyser. It reads every file of a candidate component and never imports or runs any of it. `factory.check()` calls it after manifest admission and before any test command; the report gets an `analysis` block and one `SA-xxx` finding per issue (`path:line message`).

```
from factory.analysis import analyse_component
res = analyse_component(folder, manifest_dict)   # res.issues, res.blocked, res.as_dict()
```

## Gate
A HIGH issue maps to an error finding. The component stays at `draft` at most, its declared tests are **not run** (`FAC-015`), and it can never reach `tested`. MEDIUM and LOW are warnings. An unparseable, binary, compiled or non-Python script file is a HIGH issue (fail closed), and so is an analyser crash (`SA-015`). Still a logical check, not a security boundary: see the factory sandbox note in `services/blueprint/README.md` and `docs/security/component-static-analysis.md`.

## Codes
| Code | Meaning | Typical severity |
|---|---|---|
| SA-001 | network access: socket, HTTP and mail clients, URL literals | high (modules), medium (URL) |
| SA-002 | filesystem escape: absolute or `..` path, link, chmod, delete, computed path | high or medium |
| SA-003 | subprocess, shell, process replacement | high |
| SA-004 | `eval`, `exec`, `compile` | high |
| SA-005 | dynamic import: `importlib`, `__import__`, loaders, import hooks | high |
| SA-006 | environment variables, credential files, keyrings | high |
| SA-007 | engine-internal or platform-internal imports, direct database clients | high |
| SA-008 | undeclared capability: model SDK without `dataHandling.sendsDataToModels`, component not in `requires`, third-party module | high (model SDK), medium |
| SA-009 | obfuscation: encoded blobs, decode at run time, computed `getattr`, look-alike characters, packed lines | medium or high |
| SA-010 | interpreter introspection (`__subclasses__`, `__globals__`, frames) | high |
| SA-011 | unsafe deserialisation (pickle, marshal, `yaml.load`) | high |
| SA-012 | cannot parse (invalid Python or JSON, bad UTF-8) | high (embedded script: low) |
| SA-013 | binary, compiled or non-Python script file | high |
| SA-014 | hard-coded credential or private key literal | high |
| SA-015 | analyser failure | high |

Codes are stable: never renumber, add at the end.

## What it reads
- `.py`: AST scan with import alias resolution (`import os as o`, `from os import environ`).
- `.json`: all strings checked for credential literals, credential file names and URLs under URL-like keys; strings under `script`, `code`, `server_script`, `python`, `expression`, `formula`, `condition`, `handler` are scanned as Python with the JSON line reported. Duplicate keys are all scanned.
- Other known text types: credential literals only. Anything else is SA-013.

## Limits (be blunt)
Static analysis of a dynamic language is bypassable by a determined author (for example code assembled outside any rule). It lowers the chance that a model-written component does something unintended; it does not make untrusted code safe. Third-party or customer-influenced code still needs the OS-level sandbox (INF-014) and a named reviewer (ADR-0034). Rules are tables in `rules.py`; a rule change needs a test in `tests/factory/test_analysis.py`. Secret-looking patterns are assembled at import time so no literal key is stored here.
