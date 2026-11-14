# Session log: erp-004-version-policy

Date: 2026-11-14
Author: partner
Tool and model: antigravity / gemini-4-hydrogen
Plan IDs: ERP-004

## Summary
Drafted `docs/architecture/engine-version-policy.md` for ERP-004 covering the current pinned engine/dependency set, pin immutability rules, upstream lifecycle facts cited as of 2026-11-14 (flagging MariaDB 10.6 Community EOL on 2026-07-06), upgrade classes, gate-based upgrade/rollback procedure, security exposure rules, governance interactions, and open founder decisions.

## Files touched
- `docs/architecture/engine-version-policy.md`: created the version pin and upgrade policy document (92 lines; Status: draft, Owner: partner).
- `docs/PLAN.md`: changed row `ERP-004` Status from `todo` to `doing`.
- `docs/open-questions.md`: appended open questions `Q-25`, `Q-26`, and `Q-27`.
- `docs/log/2026-11-14-partner-antigravity-erp-004-version-policy.md`: recorded session summary, checks, UNVERIFIED items, and next steps.

## Decisions
- Flagged `mariadb:10.6` (`infra/dev/docker/docker-compose.dev.yml`) as past Community EOL (`2026-07-06`) and opened `Q-25` to choose between MariaDB `11.8` LTS and `10.11` LTS before `G2`/`INF-005`.
- Proposed consolidating duplicated version pins into one machine-readable manifest and expanding `infra/dev/docker/verify_dev_bench.py` (`Q-26`).
- Proposed gate-based (date-free) security patch exposure rules and requested ratification plus a `v15` to `v16` migration trigger rule (`Q-27`).
- Left the following explicitly marked `UNVERIFIED`: Frappe source commit inside cached base image, exact Python/Node versions inside base image, non-`linux/amd64` architectures, `bench new-site` from rebuilt clean image and real-workload behaviour, Redis `7.2.7` image contents/licence reading (`Q-15`), fixed Frappe calendar patch cadence, intra-`v15` ERPNext/HRMS patch bounds, exact calendar EOL dates for MariaDB `10.11`/`11.4`/`11.8`/`12.3` and Redis `7.2`, and Frappe `v15` minimum Redis server version.

## Verification / checks
- `python3 scripts/check_repo_hygiene.py`: PASS (`Repo hygiene OK (485 files checked).`).
- `python3 scripts/check_docs.py`: exit 1 with ONLY `ERROR docs/STATUS.md is stale: run python3 scripts/build_status.py` (`0 warning(s)`, no broken links or plan/log errors; `docs/STATUS.md` left untouched for orchestrator regeneration).
- `python3 scripts/scan_secrets.py`: PASS (`secret scan: 0 hit(s)`).
- `wc -l docs/architecture/engine-version-policy.md`: `92` lines (under the 300-line cap).

## Review (orchestrator, claude-code / claude-opus-5-5, a different model from the author)
- Re-read the pinned set in section 1 against the Dockerfile, compose file, verifier and licence register: matches.
- Spot-checked the external sources on 2026-11-14: the Frappe supported-versions wiki (v14 EOL 31 January 2026, v15 end of 2027 planned, v16 end of 2029 planned), the Frappe v15 and v16 pyproject Python ranges, and the MariaDB announcement (10.6 end of life on 6 July 2026, 10.6.28 final). All match.
- Confirmed the referenced ADRs, RULES numbers and the `engine.upgrade_*` event names exist in the repo.
- Corrected: `redis~=4.5.5` is the Python client pin, not a Redis server version.
- Not checked: the Redis security policy wording and the MariaDB maintenance policy page.

## Tokens or cost
Unknown (sub-agent run; not metered inside repository).

## Next step
Orchestrator reviews `docs/architecture/engine-version-policy.md` and open questions `Q-25`–`Q-27`, regenerates `docs/STATUS.md` via `python3 scripts/build_status.py`, commits, and solicits founder decisions on `Q-6`, `Q-15`, `Q-25`, `Q-26`, and `Q-27` before marking `ERP-004` `done`.
