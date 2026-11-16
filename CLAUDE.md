@AGENTS.md

## Claude-specific notes
- Pick the tier per task from [agents/routing.md](agents/routing.md): Opus-class for architecture, security and tax logic; Sonnet-class for implementation; Haiku-class for boilerplate, search and formatting. Ask a different model to review.
- Use subagents for parallel research and independent files; give each a scoped task with acceptance criteria and have research write to `docs/research/` with sources. Do not use worktree isolation unless agents edit the same files.
- Follow [agents/working-principles.md](agents/working-principles.md) (think before coding, simplicity, surgical changes, goal-driven execution) and, when you orchestrate subagents, [agents/team-protocol.md](agents/team-protocol.md): start with three to five roles from [agents/roles.md](agents/roles.md).
- You may commit, push your feature branch and open PRs (standing permission from both founders, see AGENTS.md Branches and PRs). Never push to `main` or force-push.
- Follow [agents/working-principles.md](agents/working-principles.md) (think before coding, simplicity, surgical changes, goal-driven execution) and, when you orchestrate subagents, [agents/team-protocol.md](agents/team-protocol.md): start with three to five roles from [agents/roles.md](agents/roles.md). Follow the efficient review workflow in [agents/team-protocol.md](agents/team-protocol.md) section 14 when you prepare or review a PR.
- Do not run `git commit` or `git push` unless the session task says so.
- The founder's global vault rules (decisions and logs to the Second Brain project `AI Native ERP`) apply in addition. Repo decisions still go to `docs/decisions/` as ADRs.
