# Session log: erp-001-preflight

Date: 2026-11-11
Author: partner
Tool and model: codex / gpt-6.1-terra
Plan IDs: ERP-001

## Summary
Reviewed the ERP-001 bench and the golden path using cached image metadata; the live bench proof remains open.

## Files touched
- docs/open-questions.md: Q-16 records golden-path interface details for the contract owner to resolve.
- Generated docs/STATUS.md and this log record the preflight.

## Decisions
- No contract or gate decision. The mapping and ADR-0026 through ADR-0030 remain proposed.
- Independent reviewers: GPT-6 Astra checked the golden-path arithmetic and bench configuration; the partner's session used GPT-6.1 Terra.

## Tokens or cost
Not measured.

## Next step
ERP-001: the cached image reports Frappe 15.126.0, ERPNext 15.124.5 and HRMS 15.64.8. The HRMS tag resolves to commit 186900a6e3db4e6f927f1ee20df745bbb082638a ([upstream](https://github.com/frappe/hrms/tree/v15.64.8), accessed 2026-11-11). The Dockerfile uses a floating base tag and does not enforce the declared HRMS commit; a clean, reproducible build is UNVERIFIED. The existing verifier passed but did not prove a live site. The shared authenticated development host (INF-012) is not recorded as available; the founders were asked to provide it.

ERP-021 and ERP-022: static inspection of packaged metadata found 35 directly named mapping fields; this is not a live site or behavioral proof. The base sale's trial balance was independently recomputed at 1,150.00 on each side. Q-16 remains for the mapping owner; no accountant reviewed the scenario. Run the real adapter, permission, recovery and accounting tests when the dependencies are done.
