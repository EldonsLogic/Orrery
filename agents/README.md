# agents/

Status: accepted
Owner: eldon

Role specs and routing rules for AI agents (and humans acting in those roles). Rules of record: [../AGENTS.md](../AGENTS.md). Any tool can read these files; none depends on a tool-specific feature.

| File | Purpose |
|---|---|
| [routing.md](routing.md) | Which model tier for which job; orchestrator rules |
| [model-registry.md](model-registry.md) | Models and tools the founders use; costs |
| [orchestrator.md](orchestrator.md) | Splits work, delegates, merges results |
| [architect.md](architect.md) | Designs, writes ADRs and contracts |
| [implementer.md](implementer.md) | Writes code and config for one scoped task |
| [reviewer.md](reviewer.md) | Reviews a change with a different model than the author |
| [security-reviewer.md](security-reviewer.md) | Threat-focused review |
| [test-writer.md](test-writer.md) | Tests and evals |
| [doc-keeper.md](doc-keeper.md) | Logs, plan, status, glossary |
| [arabic-linguist.md](arabic-linguist.md) | Arabic strings, terminology, eval prompts |
| [compliance-checker.md](compliance-checker.md) | Checks against ZATCA, VAT, WPS, PDPL sources |

How to use a role: paste or point the agent at the role file plus the task (plan ID, goal, acceptance criteria, files in scope). One agent, one role, one task.
