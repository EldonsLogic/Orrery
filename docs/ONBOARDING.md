# Onboarding and lanes

Status: accepted
Owner: eldon

Everything a founder needs to start working here, with no separate message. Read it once, then work from [STATUS.md](STATUS.md). Agents: if the person you are working with has not completed section 1, walk them through it first.

## Which founder are you?
| Founder | GitHub | Log author | Lane |
|---|---|---|---|
| Eldon | `EldonsLogic` | `eldon` | Spine, product and brand |
| Partner | `sayegh9` | `partner` | Engine, runtime and compliance |

Agents: at session start work out which founder you are helping (`gh api user --jq .login`, or `git config user.name` and `user.email`, or ask). Do not assume. Use the answer for the log author, the plan-row owner and the lane. Founders: if your agent asks who you are, tell it.

## 1. One-time setup (each founder, about 30 minutes)
1. Clone the private repo (sign in with your GitHub account): `git clone https://github.com/EldonsLogic/Orrery.git`, then `cd Orrery`.
2. Install Python 3.10 or newer, then `pip install pre-commit` and `pre-commit install` (plan row GOV-010). It installs three hooks: no commit on `main` and a plan ID in every commit message, and a pre-push guard that blocks pushes to `main` and runs the repo checks. Never use `--no-verify`.
3. Run the four checks; all must pass on your machine:
   ```
   python3 scripts/build_status.py
   python3 scripts/check_docs.py
   python3 scripts/check_repo_hygiene.py
   python3 scripts/scan_secrets.py
   ```
4. Open your AI tool at the repo root and paste the starter prompt from [agents/delegation-playbook.md](../agents/delegation-playbook.md) section 8 (Claude Code reads `CLAUDE.md` by itself; for Codex and Antigravity point the tool at `AGENTS.md`).
5. Read, in this order: [AGENTS.md](../AGENTS.md), [RULES.md](RULES.md), [00-START-HERE.md](00-START-HERE.md), [STATUS.md](STATUS.md), the latest 3 files in [log/](log/README.md).
6. Never put secrets, keys, customer data, scratch files or documents outside the project in the repo; the hygiene check will fail if you do.
7. Partner, first week: review ADR-0001 to ADR-0018 (GOV-013). Open one PR that sets the `Approved by` line of each ADR you accept to "Eldon and partner"; for anything you disagree with, add an entry to [open-questions.md](open-questions.md) instead of editing the decision text. Fill in the Codex and Antigravity rows of [agents/model-registry.md](../agents/model-registry.md) (GOV-012).

## 2. Lanes (initial split; re-assign by changing the Owner in [PLAN.md](PLAN.md) in a PR)
Lanes keep two people and several agents out of each other's files. Edit only your lane's paths. If you need a change in the other lane, open an entry in [open-questions.md](open-questions.md) or comment on the other's PR. The shared interface is `contracts/`; changes there need an ADR and both founders.

| Lane | Founder | Paths | Typical plan rows |
|---|---|---|---|
| Spine, product and brand | Eldon | `contracts/`, `services/blueprint/`, `services/discovery/`, `services/operate/`, `web/`, `evals/`, `docs/product/`, `docs/brand/`, `docs/strategy/`, `docs/research/` | BPL-003 to BPL-006, QA-001 to QA-004, SEC-001, WEB, BRD, DSC, GTM, FND, LEG |
| Engine, runtime and compliance | Partner | `apps/engine/`, `infra/`, `components/`, `connectors/` | CE-SEC-003, CE-SEC-005, LEG-004, ERP, CMP, BPL-007, BPL-008, BPL-012 |
| Shared (needs the other's review) | both | `docs/PLAN.md`, `docs/RULES.md`, `AGENTS.md`, `docs/decisions/`, `docs/log/`, `docs/security/`, `docs/compliance/`, `docs/legal/`, `scripts/`, `.github/` | GOV |
| Decide at the start of G2 | both | `services/gateway/`, `services/control-plane/` | PLT |

## 3. First tasks (claim by setting `doing` plus owner in PLAN.md)
- **Eldon:** BPL-003 Blueprint validator, BPL-005 fixture (in progress), identity decision ADR-0007 (PLT-002), web stack decision (WEB-018), threat model (SEC-001), Arabic eval set (QA-001, QA-002), owner interviews (GTM-002), the founders' agreement and licence policy (LEG-001, LEG-002).
- **Partner:** finish CE-SEC-003 (policy persistence, in progress), the third-party licence register (LEG-004, it unblocks the engine spike), then ERP-001 (pin versions and stand up a bench), ERP-003 (scripted tenant creation), CMP-002 (evaluate the ZATCA app), BPL-012 (engine adapter interface).
- **Both:** GOV-010 (pre-commit), and creating the shared accounts when [ADR-0018](decisions/ADR-0018-development-environments-and-progress-viewing.md) asks (Vercel project, dev server): INF-012 and INF-013.

## 4. Decisions waiting, and who records them
| Decision | Plan ID | Who | Where |
|---|---|---|---|
| Identity: central login with per-tenant roles, or per-tenant users | PLT-002 | Eldon proposes, both approve | ADR-0007 |
| Web stack | WEB-018 | Eldon proposes, both approve | new ADR |
| Final name, logo direction, Arabic spelling | BRD-003 | both; counsel clears the name (LEG-008) | ADR |
| Founders' agreement, licence, IP assignment | LEG-001, LEG-002 | both with counsel | legal checklist |
| GitHub plan for branch protection | GOV-008 | Eldon | open questions |
| Dev server host and accounts | INF-012, INF-013 | both | ADR-0018 |

## 5. The loop for every task
1. Pick a row from "Ready to start" in STATUS.md; set it `doing` with your name; pull the latest `main`.
2. Create a branch named with the plan ID (for example `bpl-003-validator`).
3. Work, delegating scoped sub-tasks by model tier ([delegation playbook](../agents/delegation-playbook.md)).
4. Finish: new session log (`python3 scripts/new_log.py ...`), update PLAN statuses, then run `python3 scripts/finish_session.py` (regenerates STATUS, runs every check, verifies the push and the PR). Open the PR with how to view the change.
5. The other founder reviews it (with a different model than the author used). Merge only after all checks pass, by a founder or by an agent the founder has authorised (RULES.md rule 10). Nobody pushes to `main`.
6. Delete the merged branch.

## 6. When you are blocked
Stop and say exactly what is missing (an account, access, a key, a decision) and where it should go; never guess or work around it. Add the question to [open-questions.md](open-questions.md) if a founder needs to decide.
