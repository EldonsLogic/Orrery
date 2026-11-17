# Autonomy metrics: definitions, sources and reporting template

Status: draft (GOV-016)
Owner: eldon
Source of the targets: [08-product-vs-software-house.md](08-product-vs-software-house.md) (hypotheses, not benchmarks; revise after client 1).

Purpose: one place that fixes what each metric means, where its number comes from, and how it is reported each month. Numbers come from code or from logged records, never from memory (AGENTS.md principle 6). A metric with no source below is reported as "not measured", never estimated.

## Definitions and sources
| Metric | Exact definition | Source of the number | Measured by |
|---|---|---|---|
| Platform Autonomy Rate | Blueprint elements (entities, fields, workflows, roles, reports, print formats, integrations) in the applied Blueprint that the compiler produced from library components with no human edit, divided by all elements | Deterministic diff (BPL-006) between the library-produced draft and the applied revision; the exceptions register | Script, per tenant, per revision |
| Human hours per go-live | Founder and contractor hours from signed contract to production, all-in | Time log per client (hours, who, which task) | Manual log, summed by script |
| Time to go-live | Calendar span from signed contract to first production use | Contract record and go-live record | Manual dates in the client record |
| Component reuse ratio | Components used by two or more tenants, divided by all components in use | Component registry (BPL-010) and tenant Blueprints | Script |
| New components per build | Components added to the library for this client | Library change records | Count |
| Client-specific code lines | Lines outside library components and configuration | Repo scan against the lane and folder rules | Script; target stays 0 |
| Arabic eval pass rate | Pass rate of the release gate set | `python3 -m evals.harness run` report (QA-001) | Script |
| Services share of revenue | (Setup + custom) divided by total revenue | Finance records | Finance, outside the repo |
| Setup gross margin | (Setup price minus human cost) divided by setup price | Finance records and the time log | Finance, outside the repo |

Revenue and margin rows contain commercial figures: they live in the founders' private finance records, never in this repo (AGENTS.md repo hygiene). The repo report carries only the percentages, and only when a founder supplies them.

## Exceptions register (feeds the Autonomy Rate)
Every manual step is one row: tenant, Blueprint revision, element pointer, what was edited by hand, reason, class (`missing_component`, `component_gap`, `mapping_gap`, `client_specific`, `error_in_draft`), proposed automation, owner. The register is the backlog for the library. Rows are appended, never rewritten.

## Monthly report template
Copy into a new file `docs/log/` entry or the handoff note for the month. Fill every cell or write "not measured".

```
# Autonomy report: <month>
Clients live: <n>. Clients in build: <n>.

| Metric | This month | Last month | Target for this client count | Source / note |
|---|---|---|---|---|
| Platform Autonomy Rate | | | | |
| Human hours per go-live | | | | |
| Time to go-live | | | | |
| Component reuse ratio | | | | |
| New components per build | | | | |
| Client-specific code lines | | | 0 | |
| Arabic eval pass rate | | | | |
| Services share of revenue | | | | |
| Setup gross margin | | | | |

Exceptions this month: <n new>, top class: <class>, top automation candidate: <one line>.
Stall check: autonomy flat or down for two consecutive clients? yes / no. If yes, the roadmap rule applies: stop selling and fix the platform (08, principle 5).
Decisions needed from the founders: <list or none>.
```

## Rules
- A target missed is reported as missed with the cause, not rebased silently. Targets change only by a dated note in this file.
- The Autonomy Rate counts only elements the compiler emitted from library components. Hand-written elements count against it even when they are correct.
- Until the first client exists, every row reads "not measured".
