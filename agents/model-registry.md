# Model registry

Status: accepted
Owner: eldon

Models and tools the founders currently use. Costs and limits are UNVERIFIED; fill in from each vendor's current pricing page with the access date. Update when subscriptions change.

| Tool | Model family | Tier mapping | Used by | Instruction file read | Cost notes |
|---|---|---|---|---|---|
| Claude Code | Claude Fable 5.1 | Strongest (hardest planning and review) | eldon | CLAUDE.md (imports AGENTS.md) | UNVERIFIED |
| Claude Code | Claude Opus 5.5 | Strongest | eldon | CLAUDE.md | UNVERIFIED |
| Claude Code | Claude Sonnet 5.5 | Mid | eldon | CLAUDE.md | UNVERIFIED |
| Claude Code | Claude Haiku 5.5 | Small | eldon | CLAUDE.md | UNVERIFIED |
| Codex | OpenAI o3 / o1 | Strongest (architecture, complex logic) | partner | AGENTS.md | UNVERIFIED |
| Codex | OpenAI GPT-4o | Mid (implementation, refactoring) | partner | AGENTS.md | UNVERIFIED |
| Codex | OpenAI GPT-4o-mini | Small (boilerplate, docs, search) | partner | AGENTS.md | UNVERIFIED |
| Antigravity | Gemini 3.8 Pro | Strongest (architecture, review, planning) | partner | GEMINI.md (reads AGENTS.md) | UNVERIFIED |
| Antigravity | Gemini 3.8 Flash | Mid (implementation, tasks) | partner | GEMINI.md (reads AGENTS.md) | UNVERIFIED |
| Antigravity | Gemini 3.8 Flash-Lite | Small (quick checks, boilerplate) | partner | GEMINI.md (reads AGENTS.md) | UNVERIFIED |
| Claude Code | Claude 3.5 Sonnet / Opus | Strongest / Mid (per task difficulty) | partner | CLAUDE.md | UNVERIFIED |

## Product runtime models
Models the platform itself calls are chosen through the gateway after the Arabic bake-off (QA-003, [ADR-0010](../docs/decisions/ADR-0010-model-strategy.md)). Not listed here until decided.
