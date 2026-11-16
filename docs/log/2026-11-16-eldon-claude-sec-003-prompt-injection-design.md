# Session log: sec-003-prompt-injection-design

Date: 2026-11-16
Author: eldon
Tool and model: claude
Plan IDs: SEC-003

## Summary
Drafted the prompt-injection defence design (SEC-003): trust levels L0-L3 with taint propagation, instruction-hierarchy rules, tool allowlists mapped to the action-policy risk classes, egress and memory controls, 34 attack cases for QA-006 and 36 requirements (PI-001 to PI-036) for DSC-010, INF-009 and the gateway. Status stays draft; eight founder decisions are listed in the document.

Model and prompt: written by a subagent (Fable 5.2) from a scoped brief naming the one allowed file and the sections required (untrusted-content tagging, tool allowlists, no instruction following from data, deterministic-zone boundary, attack cases, requirements). The orchestrator checked the file against the brief and ran the doc checks. SEC-003 is a G1 row done early because every G0 row left in this lane is a founder task; design only, no code.

## Files touched
- docs/security/prompt-injection-defence.md: new design (draft)
- docs/PLAN.md: SEC-003 done

## Decisions
- Founder decisions D-1 to D-8 sit in the document (section 11). D-7 (trust envelope and new events are contract changes) needs an ADR and security review before any contract edit.

## Tokens or cost
Unknown or approximate, if known.

## Next step
QA-006 turns the 34 attack cases into an eval suite; DSC-010 and INF-009 must meet PI-001 to PI-036. Add the open questions Q-A to Q-H to docs/open-questions.md when a founder takes them. Some requirements name rows already done (BPL-003, BPL-006, BPL-011) and need follow-up criteria or new rows.
