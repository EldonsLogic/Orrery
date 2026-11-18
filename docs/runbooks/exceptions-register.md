# Runbook: exceptions register

Status: draft (GOV-017)
Owner: eldon

## Purpose
Every manual step in a build (a human edited a Blueprint, hand-fixed a mapping, wrote something the library lacked) is logged with a reason. The register is the backlog for the component library and the numerator behind the Platform Autonomy Rate ([autonomy metrics](../strategy/autonomy-metrics.md), [strategy 08](../strategy/08-product-vs-software-house.md) rule 3). A manual step that is not logged does not count as an exception and hides a services habit.

## Preconditions
- A tenant and a Blueprint revision exist (a build has started).
- You know the pointer of the element you changed (entity, field, workflow, role, report, print format or integration id).

## What is an exception
Anything a human did that the compiler, library or connector should have done: an edit to the draft Blueprint, a corrected mapping, a field the library lacks, a one-off for this client (the last is also a breach of "no client-specific code" and needs a reviewer). Pure configuration the product is meant to take from the owner (names, logos, prices) is not an exception.

## Steps
1. Append one row the moment you make the manual step, not later from memory. Rows are appended, never rewritten; a correction is a new row that points to the old one.
2. Fill every column: tenant id, Blueprint revision, element pointer, what was edited by hand, reason, class (`missing_component`, `component_gap`, `mapping_gap`, `client_specific`, `error_in_draft`), proposed automation, owner.
3. Never put customer data, personal data, secrets or commercial figures in a row. Use ids and pointers only.
4. Weekly, the owner of each class triages new rows: link to a plan row or an open question, or mark `wont_automate` with a reason.
5. Monthly, count rows into the autonomy report; a class that grows two months in a row gets a plan row first.

## Where the register lives
- Before any tenant exists: nowhere (empty). Do not create placeholder rows.
- From the first build: one append-only table per tenant in the private tenant record (outside this repo, because it names a client). The repo carries only the counts by class in the monthly report and the plan rows it produces.
- When the platform has a database for build records, the table becomes a Blueprint change record type and this runbook is superseded by an ADR.

## Row template
| date | tenant | blueprint rev | element pointer | edited by hand | reason | class | proposed automation | owner | follow-up |
|---|---|---|---|---|---|---|---|---|---|

## Verification
At go-live, the number of rows must match the human edits in the Blueprint history (BPL-022 reports removals); a mismatch is itself a finding.

## Rollback
Not applicable: the register is append-only. A wrong row is corrected by a new row.

## Who
The founder or agent who made the manual step writes the row; the class owner triages; the founders review counts monthly.
