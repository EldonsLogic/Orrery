# Session log: inf-013-vercel-build-tokens

Date: 2026-11-18
Author: eldon
Tool and model: claude-code
Plan IDs: INF-013

## Summary
Vercel import of web/app failed because the gitignored tokens.generated.css is only copied by the workspace build; each app's own build now copies the tokens first.

## Files touched
- web/app/package.json, web/marketing/package.json: build runs the token copy before next build

## Decisions
- None, or link to ADR / strategy decision.

## Tokens or cost
Unknown or approximate, if known.

## Next step
Eldon finishes the Vercel projects (Root Directory web/app and web/marketing); then mark INF-013 done.
