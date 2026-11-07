# Session log: enforcement-layers

Date: 2026-11-07
Author: eldon
Tool and model: claude-code
Plan IDs: GOV-024,GOV-008,GOV-010

## Summary
Founder asked for the logging and rules to be guaranteed on every task. Nothing can honestly guarantee that AI agents always comply, so this session added independent enforcement layers and recorded what stays unguaranteed. Also recorded the founder's standing authorisation for his sessions to merge PRs once checks pass.

## Files touched
- scripts/check_commit_msg.py, scripts/check_pre_push.py, scripts/finish_session.py (new): commit message must name a plan ID; no push to main plus repo checks before any push; end-of-session gate that refuses to finish until tree committed, status regenerated, checks and task trail pass, branch pushed and PR open.
- .pre-commit-config.yaml: installs commit, commit-msg and pre-push hooks; no commit on main.
- .github/workflows/main-guard.yml (new): after every push to main, re-run checks and open an issue for both founders on a direct push or failure.
- docs/decisions/ADR-0019 and INDEX; docs/RULES.md (rule 10 standing authorisation, rule 45b); AGENTS.md session end; docs/ONBOARDING.md; docs/PLAN.md (GOV-024).

## Decisions
- ADR-0019: layered enforcement. The only layer that blocks on the server is GitHub branch protection, which needs a paid plan for a private repo (GOV-008, open). Recommended.
- Standing authorisation (Eldon, 2026-11-07): his sessions merge PRs once all checks pass, including dependency-bot PRs. Dependabot PRs 1 and 2 were asked to rebase.

## Tokens or cost
Unknown.

## Next step
Founders: decide the GitHub plan (GOV-008); both run `pre-commit install` (GOV-010). Merge the Dependabot PRs after their rebase.
