# Onboarding and lanes

Status: accepted
Owner: eldon

Everything a founder needs to start working here, with no separate message. Read it once, then work from [STATUS.md](STATUS.md). Agents: if the person you are working with has not completed section 1, walk them through it first.

## Which founder are you?
| Founder | GitHub | Log author | Lane |
|---|---|---|---|
| Eldon | `EldonsLogic` (one GitHub account; he may use more than one Claude subscription or tool, one session at a time) | `eldon` | Spine, product and brand |
| Partner | `sayegh9` | `partner` | Engine, runtime and compliance |

Agents: at session start work out which founder you are helping (`gh api user --jq .login`, or `git config user.name` and `user.email`, or ask). Do not assume. Use the answer for the log author, the plan-row owner and the lane. Founders: if your agent asks who you are, tell it.

## Eldon works from several Claude sessions
All of Eldon's sessions use the one GitHub account `EldonsLogic`: same lane, same plan owner (`eldon`), same standing merge authorisation. Never run two at once. Before switching tool or subscription: finish the session (`python3 scripts/finish_session.py`, so everything is committed, pushed and in a PR) and write the log. When starting on the other session: `git pull`, read the latest log and the `doing` rows owned by `eldon` in STATUS.md, and continue from there; do not start a second branch for a row that already has one. Log the tool as `claude-code`.

## Cloud sessions
A cloud session works from a fresh clone on the provider's side. Before it starts: the tool must be connected to the founder's own GitHub account (a repo collaborator). Set `ORRERY_FOUNDER=EldonsLogic` (or tell the agent who you are) because `gh` may be missing; `finish_session.py` then warns that it could not verify the PR instead of failing, and CI re-checks everything. If the sandbox allows it, run `pip install pre-commit && pre-commit install` first; if not, CI and branch protection still enforce the rules (including a plan ID in every commit message). Name the branch with the plan ID if the tool lets you. Never leave a cloud session running while you start another session as the same founder: wait for it to report finished and for its PR to exist, then pull on the next machine.

## Founder decisions that change your work (read before you pick a task)
- **2026-11-07, ADR-0024: four phase-1 markets, no fixed launch order.** Saudi Arabia, the UAE, Egypt and Qatar are all phase 1; the first leads are in Qatar. Do not write or assume "KSA first" in code, docs or tests. For the engine lane: country packs, e-invoicing and payroll components and hosting must not hard-code three countries; Egypt and Qatar are research needed (CMP-027, CMP-030 at G1, packs CMP-028 and CMP-031 at G2). The Blueprint contract already allows country QA. Never state a Qatar or Egypt rule, rate or deadline without a source and access date.

## 1. One-time setup (each founder, about 30 minutes)
1. Clone the repo (public to read; you need collaborator access to push; sign in with your GitHub account): `git clone https://github.com/EldonsLogic/Orrery.git`, then `cd Orrery`.
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

## 2. Lanes and independent work (ADR-0025; initial split; re-assign by changing the Owner in [PLAN.md](PLAN.md) in a PR)
Lanes keep two people and several agents out of each other's files. Edit only your lane's paths. The lane map is `scripts/lanes.json` (source of truth); CI, the pre-push hook and `finish_session.py` run `scripts/check_lanes.py`, which **fails** a change that touches the other founder's lane. If you genuinely need a change there, get the other founder's agreement first (a PR comment or an entry in [open-questions.md](open-questions.md)), then add this line to your session log: `Cross-lane: approved by <eldon|partner> (where and when)`. Reviewers must confirm the agreement is real. The shared interface is `contracts/`; changes there need an ADR and both founders.

Every open plan row has exactly one owner, and the plan never makes one founder wait for the other inside a gate: a row may depend on the other founder's row only if that row is in an EARLIER gate (or done). Needs that cross lanes are met by interface rows at an earlier gate (a contract, a fake and a conformance test, or a fixture), so each side builds against the interface and the integration row comes later. `scripts/check_plan_independence.py` (run by the docs gate, CI, pre-push and `finish_session.py`) fails the build otherwise. To change an owner or gate, edit PLAN.md in a PR; the check tells you if it breaks independence.

| Lane | Founder | Paths | Typical plan rows |
|---|---|---|---|
| Spine, product and brand | Eldon | `contracts/`, `services/blueprint/`, `services/discovery/`, `services/operate/`, `services/control-plane/`, `connectors/`, `web/`, `evals/`, `docs/product/`, `docs/brand/`, `docs/strategy/`, `docs/research/` | BPL-003 to BPL-006, QA-001 to QA-004, SEC-001, WEB, BRD, DSC, GTM, FND, LEG |
| Engine, runtime and compliance | Partner | `apps/engine/`, `infra/`, `components/`, `services/gateway/` | CE-SEC-003, CE-SEC-005, LEG-004, ERP, CMP, BPL-007, BPL-008, BPL-012 |
| Shared (needs the other's review) | both | `docs/PLAN.md`, `docs/RULES.md`, `AGENTS.md`, `docs/decisions/`, `docs/log/`, `docs/security/`, `docs/compliance/`, `docs/legal/`, `scripts/`, `.github/` | GOV |

## 3. First tasks (claim by setting `doing` plus owner in PLAN.md)
- **Eldon:** BPL-003 Blueprint validator, BPL-005 fixture (in progress), identity decision ADR-0007 (PLT-002), web stack decision (WEB-018), threat model (SEC-001), Arabic eval set (QA-001, QA-002), owner interviews (GTM-002), the founders' agreement and licence policy (LEG-001, LEG-002).
- **Partner:** first, list every Frappe or ERPNext app and add-on you installed or used locally (name, source URL, version, licence, why) in your first PR as an entry for the third-party licence register (LEG-004); the repo contains only the change-engine module, not the engine installation. Then finish CE-SEC-003 (policy persistence, in progress), the third-party licence register (LEG-004, it unblocks the engine spike), then ERP-001 (pin versions and stand up a bench), ERP-003 (scripted tenant creation), CMP-002 (evaluate the ZATCA app), BPL-012 (engine adapter interface).
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
