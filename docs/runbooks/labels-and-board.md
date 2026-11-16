# Labels and project board mapping

Status: accepted
Owner: eldon

Purpose: one small label set and one board layout, both derived from [PLAN.md](../PLAN.md), so nobody invents their own. The plan row stays the source of truth; labels and the board only mirror it.

## Labels (created in the repo by GOV-019)

| Group | Labels | Use |
|---|---|---|
| Type (issue templates set these) | `task`, `bug`, `decision`, `deviation`, `spike` | One per issue |
| Gate | `gate:G0` to `gate:G5` | The plan row's gate; matches [GATES.md](../GATES.md) |
| Area | `area:GOV`, `area:SEC`, `area:BPL`, `area:DSC`, `area:ERP`, `area:CMP`, `area:INF`, `area:QA`, `area:BRD`, `area:WEB`, `area:OPR`, `area:PLT`, `area:LEG`, `area:DAT`, `area:GTM`, `area:FND` | The plan ID prefix; `CE-SEC` uses `area:SEC` |
| Review tier | `tier:1`, `tier:2`, `tier:3` | [ADR-0035](../decisions/ADR-0035-risk-tiered-review.md); `tier:3` waits for the human line-by-line review |
| Lane | `lane:eldon`, `lane:partner` | The row's owner |
| State | `blocked` | Only when a row cannot move; say why in the first comment |

Not used: priority labels (order is by dependency and gate), size labels, per-person assignee labels. GitHub's default labels (`enhancement`, `question` and so on) stay but are not required.

## PR rules

- The branch name starts with the plan ID (`gov-019-...`), the title starts with it in capitals (`GOV-019: ...`), and the PR carries one `tier:` label.
- Gate, area and lane labels are optional on PRs; they are mandatory on issues.

## Board (GitHub Projects, one board "Plan")

Board: https://github.com/users/EldonsLogic/projects/3 (linked to the repo, created by GOV-019).
Fields mirror the table columns: `Plan ID`, `Gate`, `Area`, `Owner`, `Status` (`Todo`, `In Progress`, `Done`). GitHub's built-in Status has no blocked option, so a blocked row keeps its status and carries the `blocked` label.
Filter the default view to the current gate (`Current gate:` in [GATES.md](../GATES.md)).
Rules: a card is created only for a plan row; moving a card never replaces editing the row in the PR that does the work. If they disagree, PLAN.md wins.
