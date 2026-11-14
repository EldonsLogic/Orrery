# Session log: erp-001-bench-proof

Date: 2026-11-14
Author: partner
Tool and model: claude-code / claude-fable-5-2
Plan IDs: ERP-001

## Summary
Committed the hardened ERP-001 dev bench (digest pins, enforced HRMS commit, local-only ports, tests), proved it with a clean build and a live synthetic site, and marked ERP-001 done.

## Files touched
- infra/dev/docker/Dockerfile: base image pinned by digest; the build fails when the cloned HRMS commit differs from the declared one.
- infra/dev/docker/docker-compose.dev.yml: MariaDB and Redis pinned by digest; database and Redis ports no longer published; engine bound to 127.0.0.1; no default admin password; no fixed container names.
- infra/dev/docker/entrypoint.sh, .env.example, .dockerignore, README.md: match the above.
- infra/dev/docker/verify_dev_bench.py: read-only check of an explicitly named running project and site (apps, versions, HRMS commit, Redis).
- infra/dev/docker/tests/: six test files for pins, build context, entrypoint, contract and the live verifier.
- apps/engine/README.md, docs/legal/licence-register.md: wording limited to what is verified.
- docs/PLAN.md: ERP-001 done. docs/open-questions.md: Q-6 note on what is now verified.

## Decisions
- No ADR. The partner asked in this session to commit, push and move on to the next G1 rows while the current gate is still G0; the rows have plan rows.
- Cross-model check: the bench changes were written in the earlier Codex sessions (GPT-6.1 Terra); this session verified them with Claude Fable 5.2.

## Evidence (2026-11-14, this machine, synthetic data only)
- `python3 -m unittest discover -s infra/dev/docker/tests`: 14 tests, OK, 3 skipped.
- Clean `docker compose build --no-cache engine` under a separate project name: built; the fresh image reports Frappe 15.126.0, ERPNext 15.124.5, HRMS 15.64.8 at commit 186900a6e3db4e6f927f1ee20df745bbb082638a.
- `verify_dev_bench.py` against the running project `platform-erp001-20261111b`, site `erp001.localhost`: verified apps, versions, HRMS commit and Redis.
- Not done: the clean image was not used to create a new site (the live site runs an image built on 2026-11-11 from the same pins); the Frappe source commit inside the base image is UNVERIFIED; counsel has not confirmed the Redis licence reading (Q-15); the shared dev host (INF-012) does not exist yet.

## Follow-up in the same session: Arabic runtime loading
- The ERP-006 audit found that Arabic did not load on the bench: our entrypoint replaced the upstream one, which links `sites/assets` to the image's built `assets`, and the HRMS Arabic catalogue was never compiled.
- infra/dev/docker/entrypoint.sh now creates that link; the Dockerfile compiles the HRMS Arabic catalogue at build time and fails if it is missing; a new entrypoint test checks the link.
- Evidence: 15 tests OK (3 skipped); clean no-cache build produces `hrms.mo`; with the rebuilt image against a copy of the synthetic site's config, the engine loads 16,144 Arabic strings (was 0), including HRMS labels. The running bench still uses the earlier image until it is recreated.

## Tokens or cost
Not measured.

## Next step
ERP-004 (version pin and upgrade policy) and ERP-005 (core module scope) start next, delegated to Codex and Antigravity with review by a different model. PR for ERP-001 needs the other founder's review before merge; ERP-003, CMP-002 and CMP-003 branches rebase after that.
