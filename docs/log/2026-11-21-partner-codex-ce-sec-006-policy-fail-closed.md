# Session log: ce-sec-006-policy-fail-closed

Date: 2026-11-21
Author: partner
Tool and model: codex / gpt-6.2-sol
Plan IDs: CE-SEC-006,CE-SEC-003

## Summary
The runtime policy evaluator now raises `PolicyExpressionError` when a comparison raises `TypeError`. The existing enforcer treats the error as a policy violation, including when the comparison is inside a negation or a chain. Identity comparisons now use the right-hand literal, restricted to `None`, `True` and `False` by the grammar shared by registration and evaluation.

## Files touched

- `apps/engine/change_engine/change_engine/guarded_apply/policy_expression.py` raises on a comparison type error and enforces the identity literal rule.
- `apps/engine/change_engine/change_engine/tests/test_ce_sec_003_security.py` covers comparison errors, identity validation and threshold gates. The `test_evaluation` assertion that a null margin makes an ordering comparison false moved to `test_unevaluable_comparisons_raise` with the new error expectation. The existing CI step already runs this module.
- `docs/PLAN.md` records CE-SEC-006 as done.

## Verification

- CE-SEC-003 security module with regression tests and the evaluator from `fe95ac7` returned `25 failed, 30 passed, 33 subtests passed`. The failures were the absent comparison errors and threshold-gate violations and the rejected boolean identity literals.
- The same module after the fix returned `30 passed, 58 subtests passed`. The four-file CI security suite returned `59 passed, 58 subtests passed`. The standalone policy enforcer suite returned `10 passed`.
- The Phase 4 suite returned `1 failed, 10 passed` before and after. `test_9_cross_doc_policy_passes_submitted_linked_doc` is the known failure in the suite excluded by CI pending a policy-store fixture update.
- `python3 -m pytest scripts/tests -q` returned `22 passed, 29 subtests passed`.
- The two CE-SEC-005 integration modules skipped all 15 cases without an active bench. No live HTTP check was performed.

## Decisions

- A missing field still compares as `None` with `==` and `!=`. It equals `None` and differs from a number, with no evaluation error.
- [ADR-0035](../decisions/ADR-0035-risk-tiered-review.md) puts policy enforcement in Tier 3. The PR requires human line-by-line review and a security review by a different model.

## Tokens or cost
Unknown.

## Next step
Complete the Tier 3 reviews for CE-SEC-006.
