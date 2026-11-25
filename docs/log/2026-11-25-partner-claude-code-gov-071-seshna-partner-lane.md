# Session log: gov-071-seshna-partner-lane

Date: 2026-11-25
Author: partner
Tool and model: claude-code, Sonnet child with an Opus coordinator
Plan IDs: GOV-071

## Summary
Renamed Orrery to Seshna in prose, customer-visible text and test fixtures in the partner-lane paths (apps/engine, infra, services/gateway), following Eldon's #296.

## Files touched
- apps/engine/change_engine/change_engine/hooks.py: `app_publisher` is now "Seshna".
- apps/engine/change_engine/change_engine/print_formats/bilingual_tax_invoice.py: footer uses Seshna in Latin script inside `_ltr(...)` in both halves.
- apps/engine/change_engine/change_engine/tests/test_erp_007_bilingual_tax_invoice.py: footer assertion updated.
- apps/engine/change_engine/change_engine/tests/test_erp_016_branded_templates.py: tenant-branded and default documents must contain neither "Seshna" nor "Orrery" (a legacy name must not leak either).
- apps/engine/change_engine/pyproject.toml: description prose only; package name unchanged.
- apps/engine/change_engine/PROVENANCE.md: "Orrery architecture" became "Seshna architecture"; prototype facts unchanged.
- infra/invisibility/crawler.py: default user agent is "Seshna-Invisibility-Crawler/1.0" (no test asserted the old value).
- infra/invisibility/tests/test_crawler.py: fixture server strings changed to Seshna.
- services/gateway/tests/test_edge_gateway.py: "Seshna" added to the must-not-leak list next to "Orrery".

## Kept (ADR-0066 item 7: internal identifiers are renamed under GOV-002)
- Environment variables `ORRERY_CONTRACTS_DIR` (contracts_support.py) and `ORRERY_EVSTREAM_DIR` (record_events.py and test_erp_009).
- Fixture cookie `orrery_sess=opaque` in infra/invisibility/tests/test_crawler.py: identifier-like, no test depends on it being the current name.
- Orrery assertions in test_erp_016, kept deliberately as leak checks.

## Decisions
- None. Follows ADR-0066.

## Tokens or cost
Unknown.

## Next step
GOV-002 renames the internal identifiers and the repo.
