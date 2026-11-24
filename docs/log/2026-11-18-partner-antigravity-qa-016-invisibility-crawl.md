# Session log: qa-016-invisibility-crawl

Date: 2026-11-18
Author: partner
Tool and model: antigravity / gemini-3.8-flash
Plan IDs: QA-016

## Summary
Implemented the QA-016 engine-invisibility crawler test tool and unit test suite under `infra/invisibility/` to verify ADR-0016 across pages, JS/CSS bundles, response headers, cookies, and API endpoints; row QA-016 remains `doing` until staging infrastructure is deployed (Q-167).

## Files touched
- `infra/invisibility/markers.json`: Catalog of engine markers (Frappe, ERPNext, Desk, RPC `/api/method/`, REST `/api/resource/`, `sid` session cookies, `system_user`, `X-Frappe-*` headers, WSGI/database/template error signatures) with inspection targets and rationale comments for each marker.
- `infra/invisibility/crawler.py`: Standard library crawler tool supporting `--base-url`, `--api-paths`, `--max-pages`, `--timeout`, and `--json`, checking response bodies, headers (Server, X-*, Set-Cookie) and cookies with line/column snippet reporting.
- `infra/invisibility/__init__.py`: Package export with lazy attribute loading to cleanly support CLI execution.
- `infra/invisibility/__main__.py`: CLI entrypoint for `python3 -m infra.invisibility`.
- `infra/invisibility/tests/__init__.py`: Package initialization for test suite.
- `infra/invisibility/tests/test_crawler.py`: Unit test suite using local stub HTTP servers covering clean site passing (0 findings, exit code 0), leaky site detection across all marker channels (exit code 1), same-origin restriction, max-pages capping, and CLI execution.
- `infra/invisibility/README.md`: Documentation on tool usage locally and against staging, with a disabled-until-staging note.
- `docs/open-questions.md`: Added Q-167 recording that staging is required to execute the live crawl and close QA-016.
- `docs/PLAN.md`: Claimed QA-016 row as `doing` (owner: `partner`).

## Decisions
- None. Follows accepted ADR-0016. Staging dependency recorded in Q-167.

## Tokens or cost
Unknown.

## Next step
Run crawl against real staging environment once INF-003 provisions staging infrastructure, verify zero engine markers on live staging, and close row QA-016.
