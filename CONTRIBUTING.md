# Contributing

Applies to the two founders and every AI agent working for them. Rules of record are in [AGENTS.md](AGENTS.md); this file is the short human version.

## Flow
1. Pick a `todo` row in [docs/PLAN.md](docs/PLAN.md) whose dependencies are `done`. Set it `doing` with your name.
2. Branch from `main`: `<plan-id>-<short-slug>`, for example `bpl-003-validator`.
3. Make small, reviewable changes. Docs, tests and code in the same PR.
4. Write a session log: `python3 scripts/new_log.py --author <you> --tool <tool> --slug <topic> --ids <ids>`.
5. Run `python3 scripts/check_docs.py`, `python3 scripts/scan_secrets.py`, `python3 scripts/build_status.py`.
6. Open a PR with the template. The other founder reviews, ideally using a different model than the author.
7. Squash-merge once CI is green. Never push to `main` directly after bootstrap.

## Rules in brief
- Architecture, security, contract or compliance changes need an ADR ([docs/decisions/TEMPLATE.md](docs/decisions/TEMPLATE.md)).
- Contract changes (`contracts/`) are versioned and need an ADR.
- No secrets, customer data or `.env` files. Use `.env.example`.
- UI uses tokens only, never hard-coded colours; strings go through i18n; test in Arabic RTL and in both themes.
- Cite URL and access date for external facts; mark the rest UNVERIFIED.
- Install hooks once: `pip install pre-commit && pre-commit install`.
