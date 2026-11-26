# Session log: cmp-038-slice-3-change-records

Date: 2026-11-26
Author: eldon
Tool and model: claude-code
Plan IDs: CMP-038

## Summary
CMP-038 slice 3, stacked on #351: change records for the pack index (withdrawal, floor raise, follow-up closure) in `services/control-plane/packpublish/`. Fake ports only. Written by Claude Sonnet 5.5 for Eldon.
- `propose_change` binds a change to the latest index digest; `sign_change` and `apply_change` use the same two-person rule as a publish (one market accountant plus one founder, never the same person, MFA step-up, per-signer signature in production). Shared checks were factored into `_signoff` and `_check_pair`; publish behaviour is unchanged.
- Audit is written first (PP-030); a stale index refuses (PP-061); a target that is not allowed refuses (PP-060); idempotent on the request id.
- Withdrawal keeps the entry in `withdrawn` for good, refuses the last published version, and drops that version's open follow-up. Floor raise only goes up and only to a published version. Closure only for a publishId in `followUpOpen`.
- The change record body (`country_pack_change_record`) is defined in code; the index lists it by id, kind and sha256.

## Files touched
- services/control-plane/packpublish/workflow.py, errors.py (PP-060, PP-061), ports.py and fakes.py (`commit_change`), __init__.py
- services/control-plane/tests/packpublish/test_change_records.py (13 new tests)

## Decisions
- None needing an ADR. Follow-ups: document the change record body in contracts/country-pack-store.md (assumption 5) and add a schema; one combined pass for change records that signs several changes at once is not needed yet.

## Tokens or cost
Unknown.

## Next step
CMP-038: upgrade scheduling, real ports, staff screen; CI control-plane step must install jsonschema and referencing.
