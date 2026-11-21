# Session log: opr-015-messaging-channel

Date: 2026-11-21
Author: eldon
Tool and model: claude-code / sonnet-5.5 (subagent)
Plan IDs: OPR-015

## Summary
Design for the chat messaging channel (docs/product/opr-015-messaging-channel.md): web push through the PWA first (content-free payload, deep link), WhatsApp second and opt-in (utility templates, read-only Q&A). Approvals, submits and posts are never completed in either channel; phone number is a delivery address bound in-app with a one-time code, fail closed; inbound text untrusted with read-only tools; engine-name lint on templates; cost caps; PDPL consent and STOP; 17 acceptance checks.

## Files touched
- docs/product/opr-015-messaging-channel.md: new design
- docs/PLAN.md: OPR-015 set doing (design only; build is G4)

## Decisions
- None final; channel order and the questions below are for the founders.

## Tokens or cost
About 80k tokens (subagent).

## Next step
Founders: one number across tenants, WhatsApp vs push plus in-app inbox for G4, Cloud API vs BSP, who pays, markets first (LEG-003), figures in WhatsApp, quiet hours, owner control over staff use. UNVERIFIED: Meta opt-in and 24-hour window rules, per-country rates, residency and processor terms, iOS push behaviour; all caps are placeholders.
