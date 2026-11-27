# services/studio

Status: draft (local founder tool, no plan row yet). Owner: unassigned (path not in `scripts/lanes.json`).

A local web app that runs the platform end to end on the code merged today, so a founder can click through it. Nothing is recorded: every request runs the real code again. State lives in memory for one server process; nothing is written to disk. Synthetic data only (the BPL-005 fixture and the DAT-002 datasets).

## Run
From the repo root (needs `pip install -r services/blueprint/requirements.txt`, Python 3.9 or later):
```
python3 -m services.studio                 # http://127.0.0.1:8765/
python3 -m services.studio --port 9000     # another port
python3 services/studio/__main__.py        # same, as a script
```
It binds `127.0.0.1` only. `--host` with any non-loopback address is refused unless `--allow-non-loopback` is also passed. `--verbose` logs request paths (never bodies). Stop with Ctrl+C.

Engine: `STUDIO_ENGINE=fake` (default) uses the in-memory fake adapter (BPL-025). `STUDIO_ENGINE=module:factory` names a zero-argument factory that returns an `AdapterHarness` ([adapter README](../blueprint/adapter/README.md), contract section 15.1), so the real adapter (BPL-012) can be plugged in later. If it cannot be imported or built, the server refuses to start. The UI badge says "In-memory engine (fake)" so nobody mistakes it for the real engine.

Tests: `python3 -m pytest services/studio -q` (or `cd services/studio && python3 -m pytest -q`). They start the server on an ephemeral loopback port. The QR and dictionary tests run `node` and are skipped if Node is not installed.

## What the UI shows
- Left, the editor: company legal and trade names (Arabic and English), component switches grouped by area with "required by" hints, entity labels, and the primary brand colour (picker and hex field).
- Compile tab: recompiles on every change (debounced). OK with step count and artifact id, or the compiler's refusals with code, JSON pointer and a plain-language hint. Steps table filterable by kind.
- Apply tab: Apply, Roll back, and Apply with a simulated failure at step N. Stage ticks, steps applied, post-conditions, plan verdict, simulated approvals, predicted versus actual export hash, and what the site now contains.
- Brand tab: the resolver's light and dark tokens applied as CSS variables to two preview boxes only; adjustments, warnings and refusals by code. A refused colour keeps the platform colour.
- Invoice tab: Saudi Arabia, UAE, Egypt, Qatar; English or Arabic (right to left, Western digits); lines and totals exactly as stored in the dataset; the Phase 1 QR payload from the real encoder, decoded, as a QR image drawn by a small local encoder (`static/qr.js`) and as copyable base64.

## API (JSON; errors are `{"ok": false, "error": {"code", "path"}}`, refusals are 409 with codes and paths)
| Method and path | Does |
|---|---|
| `GET /api/state` | Blueprint summary, components with eligibility and dependencies, engine badge, site status |
| `PUT /api/blueprint/company` | `{"legalName": {"ar","en"}, "tradeName": {"ar","en"}}` (either or both) |
| `PUT /api/blueprint/components` | `{"id", "enabled": true|false}` |
| `PUT /api/blueprint/entities/<id>/labels` | `{"ar", "en"}` |
| `PUT /api/blueprint/branding` | `{"primaryColour": "#RRGGBB"}` |
| `POST /api/compile` | real `compile_blueprint` (sandbox): artifact id and steps, or refusals |
| `POST /api/apply` | provision if needed, preview, plan, apply; optional `{"failAtStep": N}` |
| `POST /api/rollback` | real rollback of the last apply |
| `GET /api/export` | counts and names from the engine's exported configuration |
| `POST /api/theme` | `resolve_tokens` on the current branding (allow-listed keys) |
| `GET /api/invoice?market=ksa|uae|egy|qat&lang=en|ar[&invoice=INV-0001]` | dataset invoice and its QR payload |
| `POST /api/reset` | fixture Blueprint and a fresh site |

Security: loopback bind, `Host` must be loopback, `Origin` (when sent) must match, writes need `Content-Type: application/json`, 1 MB body limit, strict JSON (no duplicate keys, no NaN), CSP `default-src 'self'` (Google Fonts allowed for styles and fonts, system fonts otherwise), `nosniff`, `no-store`. No stack traces leave the process. A response that would contain the engine's name is replaced by `STUDIO-ENGINE-NAME` (ADR-0016). The client builds every element with `textContent`; a test fails if the static JS uses an HTML sink.

## Known limits
Open questions are numbered in [`__init__.py`](__init__.py). In short: the first apply is an initial build, which the contract does not let you roll back; later applies are incremental (against the engine-form Blueprint last applied) and roll back one revision at a time, unless a step is irreversible; the simulated failure shows the automatic undo; the apply path compiles an engine-targeted copy, so its artifact id differs from the Compile tab; compiles run as sandbox; approvals are granted automatically; the QR timestamp is the dataset's invoice date. The figures are synthetic test expectations, not tax output.
