# Session log: erp-020-review-fixes

Date: 2026-11-19
Author: partner
Tool and model: codex / gpt-6.1-sol
Plan IDs: ERP-020

## Summary
Completed the ERP-020 request-guard review fixes from the interrupted Claude/Codex work; kept the row doing for independent re-review. Both guard layers use the same environment credentials and deny dispatch parameters before engine initialization.

## Files touched
- `api/route_guard.py`, `wsgi.py`: bound and screen request bodies before engine dispatch, reject legacy/controller RPC parameters, allow only four read-only business DocTypes, reject site-selection headers, plain errors and a sanitized GET-only probe.
- Guard regression suites: restored saved tests, corrected the protected Session expectation, exercised the actual WSGI application and hook registration, and verified startup tokens and rotation overlap.
- Headless compose, Dockerfile and entrypoint: hash-pinned build backend, offline startup installation, all attached networks internal, startup credential validation. Default developer build remains unchanged.
- Headless smoke suite: 58 live checks, including the original JSON/form bypasses on otherwise-allowed paths, allowed authenticated positive controls, no published port and inspection of every attached network.
- `HEADLESS.md`, CI test wiring and the licence register: describe the interim service credential, record dependencies, run guards in CI. No ERP-002 files changed.

## Decisions
- Implements ADR-0016 ingress protection only; full invisibility for allowed business responses still depends on PLT-024/QA-016. No accepted ADR was edited.
- The bench-wide token is explicitly an interim G1 control, not the SEC-002 workload identity. Rotation supports an explicit previous-token overlap; operators remove it after migration.
- No entropy heuristic: credentials must be generated with secure randomness; token shape/length validation cannot prove entropy.
- Fix diff exceeds the roughly 400-line guideline because it includes the recovered body-parser regression matrix and network/startup verification. These changes close the reviewed bypasses together; size remains visible for review.

## Tokens or cost
Unknown.

## Next step
Gemini independent security re-review on the pushed head, then founder review. ERP-020 stays doing; no merge or phase exit claimed.

## Verification

- Guard suites: 63 tests pass using Werkzeug 3.1.3 and pydantic 2 in an isolated uv environment.
- Compose contract: 9 tests pass. Before network changes, 3 tests failed on egress/target mismatches.
- Live smoke: 58 PASS on a newly built headless image and a synthetic ERPNext/change-engine tenant. The unique stack was removed after the run.
- Two mutations: removing the WSGI wrapper fails the application-entry test; removing the registered hook fails its registration test. Original source bytes restored in finally blocks.
- Documents, hygiene, secrets and shell syntax checks passed. No staging gateway or tenant workload identity was tested.
- Build dependency source: [flit_core release metadata](https://pypi.org/project/flit-core/3.12.0/), accessed 2026-11-19; wheel version/hash and BSD-3-Clause licence recorded in the licence register.
