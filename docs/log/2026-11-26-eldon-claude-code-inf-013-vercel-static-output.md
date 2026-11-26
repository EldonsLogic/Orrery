# Session log: inf-013-vercel-static-output

Date: 2026-11-26
Author: eldon
Tool and model: claude-code (Claude Opus 5.5)
Plan IDs: INF-013

## Summary
The first Vercel deploy of `web/app` built but failed with NEXT_NO_ROUTES_MANIFEST: the `nextjs` preset looks for a server build in `out/`, but the app is a static export (`output: 'export'`, ADR-0022). Setting `framework` to `null` makes Vercel serve `out/` as static files.

## Files touched
- `web/app/vercel.json`: `framework` from `nextjs` to `null`.

## Decisions
- None, or link to ADR / strategy decision.

## Tokens or cost
Unknown or approximate, if known.

## Next step
Eldon redeploys the `seshna-app` project; then WEB-019 and QA-017.
