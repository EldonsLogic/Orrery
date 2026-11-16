# Session log: adapter-contract-0-1-2

Date: 2026-11-16
Author: eldon
Tool and model: claude-code (Opus-class)
Plan IDs: BPL-026

## Summary
Engine adapter contract 0.1.2 resolves the open questions the partner's review of PR 56 found blocking (Q-36 to Q-40), as a patch-level clarification on the draft contract branch (PR 40).

## Files touched
- contracts/engine-adapter.md: version 0.1.2; "no effect" = no change to engine data, refusal events listed per case (8.2 table, section 14, ADP-C-008, 010, 034 to 037, 040, 042, 052, 053); operation record created when `acquire` succeeds (5.6.1); initial-build compensation (5.6.2, new ADP-C-071); `site.applied` after rollback (5.7, ADP-C-051); `exportedProperties` key names (5.1, ADP-C-013); harness methods and semantics including `plan_evidence` and `execution_journal` (15.1); change log (18).
- contracts/README.md: engine adapter version 0.1.2.
- docs/open-questions.md: Q-45 to Q-49 appended, one RESOLVED PROPOSAL per Q-36 to Q-40.

## Decisions
- Q-36: reading (a). Rejected apply or rollback in `inspect` emits one `blueprint.apply_failed`; 4.2 refusals one `permission.denied`; other pre-record refusals nothing.
- Q-37: keep the key pattern; keys fixed, `settings_intl` for Blueprint `i18n`.
- Q-38: all harness extensions are in 15.1 and required.
- Q-39: record exists after `acquire` (key lookup, lock, record); `site.applied` after rollback = artifact rolled back to.
- Q-40: initial-build compensation is journal-derived removal (quarantine or disable, settings set back), no data dropped.
- Patch bump, no ADR (contracts README rule 2: clarifications). Partner review on PR 40 accepts or rejects.

## Tokens or cost
Unknown.

## Next step
Merge into bpl-025-fake-adapter and align the fake and the suite (BPL-025); partner reviews PR 40 and PR 56.
