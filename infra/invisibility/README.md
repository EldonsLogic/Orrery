# Engine invisibility crawl test (QA-016)

Status: draft
Owner: partner
Gate: G1
Reference: [ADR-0016: The engine is invisible to customers](../../docs/decisions/ADR-0016-engine-invisibility.md)

## Purpose

Automated crawl testing tool verifying engine invisibility across all customer-visible surfaces per ADR-0016. No external observer, tenant user, or client application must observe engine markers (Frappe, ERPNext, Desk, RPC `/api/method/`, REST `/api/resource/`, `sid` session cookies, `system_user` markers, `X-Frappe-*` headers, or internal backend stack traces) on pages, linked JS/CSS bundles, response headers, cookies, or API responses.

## Architecture

The tool consists of:
- `infra/invisibility/markers.json`: structured catalog of engine markers, match types (`substring`, `regex`, `exact`), inspection targets (`body`, `header_name`, `header_value`, `cookie_name`, `cookie_value`), and comments explaining why each marker exists.
- `infra/invisibility/crawler.py`: same-origin crawler using Python standard library only (`urllib.request`, `html.parser`, `http.cookies`). Takes `--base-url`, crawls same-origin pages and discovered JS/CSS bundles, checks configurable API paths, inspects all responses (including redirects and error status codes), and exits non-zero if any marker is detected.
- `infra/invisibility/tests/test_crawler.py`: unit test suite running against local stub HTTP servers:
  1. Clean site test: verifies 0 findings and exit code 0 when crawling HTML, CSS bundles, JS bundles, and API endpoints.
  2. Leaky site test: verifies that leaks in headers (Server, X-Frappe-*), cookies (sid, system_user), HTML bodies, stylesheets, scripts, and error envelopes are detected and reported with exact URLs and locations.
  3. Same-origin constraint test: verifies that external links are ignored.
  4. Max-pages constraint test: verifies that crawling halts at `--max-pages`.
  5. CLI test: verifies `--json` format and non-zero exit code on failure.

## How to run

### Unit tests (local stub servers)

Run the automated test suite with standard library unittest:
```bash
python3 -m unittest discover -s infra/invisibility/tests -v
```

### Against a local gateway now

When running a local dev gateway (for example on port 8080):
```bash
python3 -m infra.invisibility \
  --base-url http://localhost:8080 \
  --api-paths /api/v1/health,/api/v1/auth/session \
  --max-pages 50
```

To output machine-readable JSON:
```bash
python3 -m infra.invisibility \
  --base-url http://localhost:8080 \
  --api-paths /api/v1/health \
  --json
```

### Against staging later

When staging infrastructure is deployed (under INF-003):
```bash
python3 -m infra.invisibility \
  --base-url "$STAGING_URL" \
  --api-paths /api/v1/health,/api/v1/auth/session \
  --max-pages 100
```

## Disabled-until-staging note

Staging does not exist yet (INF-003 / ADR-0018). Staging hosts must not be invented or assumed. The crawler tool and its unit tests are fully implemented and verified locally, but plan row QA-016 remains open (`doing`) until real staging infrastructure is deployed and the test is executed against the live staging URL. This requirement is tracked in [docs/open-questions.md](../../docs/open-questions.md) as question Q-146.
