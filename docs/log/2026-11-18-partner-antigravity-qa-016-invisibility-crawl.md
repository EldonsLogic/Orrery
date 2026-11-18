# Session log: qa-016-invisibility-crawl

Date: 2026-11-18
Author: partner
Tool and model: antigravity / gemini-3.8-flash
Plan IDs: QA-016

## Summary
Implemented the QA-016 engine-invisibility crawler test tool and unit test suite under `infra/invisibility/` to verify ADR-0016 across pages, JS/CSS bundles, JS chunks and source maps, response headers, cookies, authenticated endpoints, and API endpoints; row QA-016 remains `doing` until staging infrastructure is deployed (Q-215).

## Files touched
- `infra/invisibility/markers.json`: Catalog of engine markers (Frappe, ERPNext, Desk, RPC `/api/method/`, REST `/api/resource/`, `sid`/`user_id`/`full_name`/`user_image` session cookies, `system_user`, `X-Frappe-*` headers, `cur_*` globals, `bootinfo`, `_liked_by`/`_user_tags`/`_assign`/`_comments`/`_seen` metadata fields, Python tracebacks, WSGI/database/template error signatures) with inspection targets and rationale comments for each marker.
- `infra/invisibility/crawler.py`: Standard library crawler tool supporting `--base-url`, `--api-paths`, `--auth-header`, `--cookie`, `--max-pages`, `--timeout`, and `--json`, checking response bodies, headers (Server, X-*, Set-Cookie), redacted cookies, JS chunks and source maps, clamping redirects to same-origin, and failing closed on network/HTTP/URL/regex errors.
- `infra/invisibility/__init__.py`: Package export with lazy attribute loading to cleanly support CLI execution.
- `infra/invisibility/__main__.py`: CLI entrypoint for `python3 -m infra.invisibility`.
- `infra/invisibility/tests/__init__.py`: Package initialization for test suite.
- `infra/invisibility/tests/test_crawler.py`: Unit test suite using local stub HTTP servers covering clean site passing, leaky site detection, fail-closed connection/HTTP/URL/regex checks, unparseable `Set-Cookie` and cookie value redaction, same-origin redirect clamping, JS chunks/source maps, authenticated crawl pass, max-pages capping, and CLI execution.
- `infra/invisibility/README.md`: Documentation on tool usage locally and against staging, with a disabled-until-staging note.
- `.github/workflows/tests.yml`: Added CI execution of `infra/invisibility/tests`.
- `docs/open-questions.md`: Added Q-215 (renumbered after merging `origin/main` through Q-209) recording that staging is required to execute the live crawl and close QA-016.
- `docs/PLAN.md`: Claimed QA-016 row as `doing` (owner: `partner`).

## Decisions
- None. Follows accepted ADR-0016. Staging dependency recorded in Q-215.

## Tokens or cost
Unknown.

## Next step
Run crawl against real staging environment once INF-003 provisions staging infrastructure, verify zero engine markers on live staging, and close row QA-016.
