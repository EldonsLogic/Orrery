# Session log: erp-010-stuck-application

Date: 2026-11-21
Author: partner
Tool and model: codex
Plan IDs: ERP-010

## Summary
Addressed the Tier 3 blocker on PR #201 so an authorised retry can fill the missing applicant principal on an open leave application and an independent HR Manager can then decide it.

## Files touched
- `components/core/hrms_skeleton/service.py` repairs a missing principal under the existing record lock using the same filing permission and verified employee-link checks as creation.
- `components/core/hrms_skeleton/access.py` documents the write-once identity store and its missing-value representations.
- `components/core/hrms_skeleton/tests/test_service_hardening.py` covers a one-time write failure, an existing principal, and missing create permission.
- `components/core/hrms_skeleton/manifest.json` labels the fake-engine test suite as unit tests.

## Decisions
- Used the review's retry repair option because the shared store interface has no savepoint API. The protected store still rejects overwrites.

## Tokens or cost
Unknown.

## Next step
ERP-010 remains in progress pending renewed Tier 3 review. Live bench verification is tracked in Q-475.
