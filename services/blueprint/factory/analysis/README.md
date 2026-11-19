# Static analysis for factory-built components (SEC-010)

Deterministic, standard-library-only analyser. It reads every file of a candidate component and never imports or runs any of it. `factory.check()` calls it after manifest admission and before any test command; the report gets an `analysis` block and one `SA-xxx` finding per issue (`path:line message`).

```
from factory.analysis import analyse_component
res = analyse_component(folder, manifest_dict)   # res.issues, res.blocked, res.as_dict()
```

## Gate
A HIGH issue maps to an error finding. The component stays at `draft` at most, its declared tests are **not run** (`FAC-015`), and it can never reach `tested`. MEDIUM and LOW are warnings. An unparseable, binary, compiled or non-Python script file is a HIGH issue (fail closed), and so is an analyser crash (`SA-015`). Still a logical check, not a security boundary: see the factory sandbox note in `services/blueprint/README.md` and `docs/security/component-static-analysis.md`.

## Posture: allow-list
After the Tier 3 review of PR #172 the analyser allows a small known-safe surface and refuses the rest:
- **Imports** (`SAFE_MODULES` in `rules.py`): `__future__`, `abc`, `base64`, `bisect`, `calendar`, `collections`, `contextlib`, `copy`, `csv`, `dataclasses`, `datetime`, `decimal`, `difflib`, `enum`, `fractions`, `functools`, `hashlib`, `heapq`, `hmac`, `html`, `io`, `itertools`, `json`, `math`, `numbers`, `os` (only `os.path` helpers and separators), `pathlib`, `pprint`, `random`, `re`, `secrets`, `statistics`, `string`, `textwrap`, `time`, `typing`, `unicodedata`, `unittest` (not `unittest.mock`), `uuid`, `zoneinfo`, and `pytest` (the test runner). Also allowed: `components.<id>` for the component's own id and every `requires` entry, modules the component ships, and relative imports that stay inside it. Every other import is HIGH `SA-008`, including model SDKs (models are reached through the platform) and unknown third-party modules. Left out on purpose: `sys`, `logging`, `operator`, `types`, `inspect`, `asyncio`, `threading`, `shutil`, `tempfile`, `subprocess`, `importlib`. Widening the list needs an ADR and a test.
- **Builtins**: `eval`, `exec`, `compile`, `__import__`, `globals`, `locals`, `vars`, `breakpoint`, `input` and `help` are HIGH when called. `open`, `getattr`, `setattr` and `delattr` may be called directly, with their own checks. Any other reference to these names (alias, argument, return value, decorator) is HIGH, and so is rebinding them (assignment, import alias, parameter, function or class name).
- **Dunders**: any dunder name or attribute is HIGH except plain data (`__name__`, `__doc__`, `__file__`, `__all__`, `__version__`, `__qualname__`, `__module__`) and common dunder methods called directly (`super().__init__()`). Format strings that walk into `_` attributes are HIGH.
- **Modules as values**: passing or aliasing an imported module (`x = os`, `(os,)[0]`), `getattr` on a module, and star imports are HIGH.
- **Source**: a `.py` file is parsed from its raw bytes. A coding line other than utf-8 is HIGH (the interpreter would read different text). A module or package that shadows a standard or test-runner module (component root, or a test folder without `__init__.py`) is HIGH. A folder counts as a local package only if it holds `.py` files.
- **Test runner**: `conftest.py`, `pytest.ini`, `tox.ini`, `setup.cfg`, `pyproject.toml`, `setup.py`, `sitecustomize.py`, `usercustomize.py`, `__main__.py` and `*.pth` files are HIGH whatever they hold, as is a `>>>` doctest prompt in any text file and an extensionless `#!` script. The runner also isolates pytest (`commands.py`): `-c` an empty config, `--noconftest`, `-o addopts=`, `-p no:doctest`, `-p no:cacheprovider` and `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`.

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
| SA-008 | import outside the allow-list (model SDK, component not in `requires`, third-party or unlisted standard module), relative import leaving the component, module shadowing | high |
| SA-009 | obfuscation: computed or module `getattr`, builtin rebinding, module aliasing, star import (high); encoded blobs, decode at run time, look-alike characters, packed lines (medium) | high or medium |
| SA-010 | interpreter introspection: dunder names and attributes, frames, format-string attribute walks | high |
| SA-011 | unsafe deserialisation (pickle, marshal, `yaml.load`) | high |
| SA-012 | cannot parse (invalid Python or JSON, bad UTF-8) | high (embedded value under `code`: low) |
| SA-013 | binary, compiled or non-Python script file, non-utf-8 coding line, test-runner config, doctest text, embedded non-Python script | high |
| SA-014 | hard-coded credential or private key literal (a credential-like name needs a key-like value: 12+ characters, no spaces, two character classes, high entropy) | high |
| SA-015 | analyser failure | high |

Codes are stable: never renumber, add at the end.

## What it reads
- `.py`: AST scan with import alias resolution (`import os as o`, `from os import environ`).
- `.json`: all strings checked for credential literals, credential file names and URLs under URL-like keys; strings under `script`, `code`, `server_script`, `python`, `expression`, `formula`, `condition`, `handler` are scanned as Python with the JSON line reported. One that does not parse as Python is HIGH `SA-013` (JavaScript, templates), except under `code`, which usually holds an identifier (LOW). Any script in an object whose `doctype` is a client-side type (`Client Script`, `Web Page`, `Print Format` and similar) or whose `language` is not Python is HIGH. Duplicate keys are all scanned.
- Other known text types: credential literals only. Anything else is SA-013.

## Limits (be blunt)
Static analysis is defence in depth, not the boundary. The boundary is the OS-level sandbox (INF-014) plus a named reviewer; a component that passes can still never go above `tested`. Static analysis of a dynamic language is bypassable by a determined author (for example code assembled outside any rule). Known gaps, deferred: computed `pathlib` paths (`Path(p).write_text`, review M2) are not flagged; computed format strings and `string.Formatter` are not checked; `uuid.getnode` may run a fixed system command; pytest's `monkeypatch.setattr("mod.name", ...)` imports by name and is not tracked. The evasion corpus is `tests/factory/test_analysis_evasions.py`. It lowers the chance that a model-written component does something unintended; it does not make untrusted code safe. Third-party or customer-influenced code still needs the OS-level sandbox (INF-014) and a named reviewer (ADR-0034). Rules are tables in `rules.py`; a rule change needs a test in `tests/factory/test_analysis.py`. Secret-looking patterns are assembled at import time so no literal key is stored here.
