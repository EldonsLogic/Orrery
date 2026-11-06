# Orrery (working name)

An AI-native business platform for owner-led companies in the Middle East. One chat, in Arabic or English, interviews the owner, drafts a Blueprint of the business, assembles an ERP from vetted components, simulates a month before go-live, then runs it. The name "Orrery" is a working codename and is not trademark-cleared.

Status: pre-build. See the current gate in [docs/GATES.md](docs/GATES.md) and live progress in [docs/STATUS.md](docs/STATUS.md). Private repository; not open source.

## Start
- Humans and agents: [docs/00-START-HERE.md](docs/00-START-HERE.md), then [AGENTS.md](AGENTS.md).
- Work list: [docs/PLAN.md](docs/PLAN.md). Decisions: [docs/decisions/INDEX.md](docs/decisions/INDEX.md). Risks: [docs/risks.md](docs/risks.md).
- Contributing: [CONTRIBUTING.md](CONTRIBUTING.md). Security: [SECURITY.md](SECURITY.md). Licences: [NOTICE.md](NOTICE.md).

## Layout
`docs/` documentation and plan, `contracts/` interface schemas, `apps/engine/` Frappe apps, `services/` AI and control-plane services, `web/` marketing site and app, `connectors/`, `components/`, `agents/` role specs, `evals/`, `infra/`, `scripts/` docs tooling.

## Checks
```
python3 scripts/check_docs.py
python3 scripts/scan_secrets.py
python3 scripts/build_status.py
```
