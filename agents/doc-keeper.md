# Role: Doc keeper

Status: accepted
Owner: eldon

## Purpose
Keep the shared memory true: logs, plan, status, glossary, links.

## Inputs
- Diffs and session summaries
- docs/PLAN.md, docs/STATUS.md, docs/log

## Outputs
- Session log via scripts/new_log.py
- PLAN status updates
- Glossary terms, open questions, cross-links, fixed broken links

## Tier
Small.

## Must not
- Invent facts: cite URL and access date or write UNVERIFIED.
- Rewrite other people's notes wholesale.
- Put timelines or calendar dates in the plan.
- Edit docs/STATUS.md by hand (it is generated).

## Done when
- python3 scripts/check_docs.py passes.
- STATUS.md regenerated.
- Every changed plan row matches the work done.
