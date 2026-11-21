# Session log: cmp-005-merge-ci-pin

Date: 2026-11-21
Author: partner
Tool and model: opencode
Plan IDs: CMP-005

## Summary
Merged main into the CMP-005 branch so the Hijri date tests run under the path-filtered CI, and made the `hijridate` pin explicit in the engine suite.

## Files touched
- `.github/workflows/tests.yml`: resolved the merge against main's path-filtered version, kept main's job layout, added the `Umm al-Qura entry, companion fields and print tests (CMP-005)` step after ERP-007 (same `if:`, `env:` and indentation), and appended `"hijridate==2.6.0"` to the engine suite's `pip install` line.
- `docs/log/2026-11-21-partner-opencode-cmp-005-merge-ci-pin.md`: this log.

## Decisions
- Pinned `hijridate==2.6.0` explicitly in the engine suite's install line (same pin as `apps/engine/change_engine/pyproject.toml`). Eldon's 2026-11-19 re-review found the job only received the package indirectly, which would break silently if another requirement dropped it.

## Tokens or cost
Not tracked for this session.

## Next step
Still open for CMP-005: a real-bench check of `before_update_after_submit`, the founder line-by-line and compliance reviews, and the Arabic copy review. No other work is blocked on this branch.
