# Session log: web-020-studio

Date: 2026-11-17
Author: eldon
Tool and model: claude
Plan IDs: WEB-020

## Summary
WEB-020: the Studio, a local live app (`python3 -m services.studio`, port 8765, loopback only) on the code merged today. Edit a Blueprint (company names, components, entity labels, tenant colour); the real compiler recompiles on every change and shows refusals with codes and plain hints; Apply runs plan, preview, approvals and apply on the in-memory engine (85 of 85 steps, 105 of 105 post-conditions, export hash matches); the Brand tab runs the real token resolver; the Invoice tab shows four markets in English and right-to-left Arabic with the dataset's stored figures and the real Phase 1 QR payload (own QR encoder, checked by an independent decoder in the tests). 68 Studio tests; the whole services suite passes (1272). The real adapter plugs in with `STUDIO_ENGINE=module:factory` when BPL-012 lands.

Limits, stated plainly: the engine is the in-memory fake (badge shown), not the real one; there is no login, persistence or real approval step; rollback of a first build is refused by the contract (a simulated failed apply shows compensation instead); the VAT rate and totals are synthetic test expectations; the QR is not verified against the ZATCA sandbox. Open questions Q-76 to Q-82. I started the server and used it in the browser pane (live refusal on removing a component, then apply).

Also: `services/studio/` added to Eldon's lane in `scripts/lanes.json`.

Model and prompt: Claude Opus subagent from a scoped brief (new package `services/studio/` only; live computation, no recorded data; loopback only; no innerHTML; engine pluggable). Orchestrator ran the whole services suite (1272 passed) and used the app in the browser pane. Not rigid-zone: it shows figures stored in the dataset and computes none.

## Files touched
- services/studio/: server, session, engine hook, static UI (en/ar), QR encoder, tests
- scripts/lanes.json: services/studio/ in the eldon lane
- docs/open-questions.md: Q-76 to Q-82
- docs/PLAN.md: WEB-020 added and done

## Decisions
- None; open questions Q-76 to Q-82.

## Tokens or cost
Unknown or approximate, if known.

## Next step
Point the Studio at the real adapter when BPL-012 lands (STUDIO_ENGINE); BPL-027 integration; the real web app (WEB-018 stack decision) replaces the Studio.
