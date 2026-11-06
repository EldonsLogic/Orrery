# Session logs

Status: accepted
Owner: eldon

One file per working session, per person, per tool. This replaces a shared handoff file, so two founders on different models never edit the same file and never conflict.

- Create with `python3 scripts/new_log.py --author eldon --tool claude-code --slug short-topic --ids GOV-001,SEC-002`.
- Name pattern: `YYYY-MM-DD-<author>-<tool>-<slug>.md`.
- Fill every header field (`Date`, `Author`, `Tool and model`, `Plan IDs`), then Summary, Files touched, Decisions, Next step.
- The first non-empty line under `## Summary` is shown in [../STATUS.md](../STATUS.md); make it one clear sentence.
- Logs are append-only history; fix mistakes in a later log, not by rewriting an old one.
- CI requires a new log file in any pull request that changes files outside `docs/` and `.github/`.
