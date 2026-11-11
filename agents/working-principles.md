# Working principles for every agent

Status: accepted
Owner: eldon

Four habits every agent follows in this repo, whatever the tool or model. They sit under [../AGENTS.md](../AGENTS.md) and [../docs/RULES.md](../docs/RULES.md): if a rule there is stricter, the rule wins.

Reference: the guidelines in the public repository `multica-ai/andrej-karpathy-skills` (file `CLAUDE.md`, read 2026-11-11), which summarise common coding-agent mistakes noted by Andrej Karpathy. GitHub shows no licence for that repository, so nothing is copied; the ideas are restated here in our own words and tied to our rules. Its text can change; this file is the version we follow.

## 1. Think before coding
- State your assumptions and the reading of the task you chose. If two readings are plausible, say so and ask; put founder-level questions in [../docs/open-questions.md](../docs/open-questions.md) instead of guessing.
- Say when a simpler approach exists, and take it unless the task needs more.
- If you do not understand the request or the code around it, stop and ask before you write anything.

## 2. Simplicity first
- Write the least that solves the stated task. No features nobody asked for, no abstraction for a single use, no settings or options that are not required now.
- No handling for situations that cannot happen. If the result is far longer than the task needs, rewrite it shorter.
- This is the same instinct as "configuration over code" (RULES 20) and "reuse before invention": prefer what the engine, the library or a component already does.

## 3. Surgical changes
- Touch only what the task requires. Match the style of the surrounding code, even where you would write it differently.
- Do not tidy, reformat or refactor neighbouring code. Mention unrelated problems in the log or an open question instead of fixing them.
- Remove only the leftovers your own change created (unused imports, dead variables). Leave older dead code alone unless asked.
- Every changed line should trace to the task. This is why lanes, one writer per path and small PRs exist ([../AGENTS.md](../AGENTS.md)).

## 4. Goal-driven execution
- Turn the task into a checkable goal before you start: a failing test that reproduces a bug and then passes, a validation that must pass, a measured number that must improve.
- For multi-step work, write a short plan where each step has its own check, then loop until every check passes. Report what you verified and what you could not.
- Weak goals such as "make it work" are not enough; ask for or write the acceptance criteria first (see [delegation-playbook.md](delegation-playbook.md) section 3).

## Signs it is working
- Diffs are small and every line is explained by the task.
- Fewer rewrites caused by over-building.
- Questions arrive before the work, not after a wrong build.
- Each change comes with the check that proves it.

## Where this is enforced
These are habits, not scripts. The mechanical parts are already enforced: lane guard, one plan row per task, hygiene check, task trail, and the phase exit check ([../docs/GATES.md](../docs/GATES.md)). Reviewers (a different model than the author) look for the habits above and send back changes that break them.
