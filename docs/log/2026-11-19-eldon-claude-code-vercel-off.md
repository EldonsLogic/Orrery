# Session log: vercel-off

Date: 2026-11-19
Author: eldon
Tool and model: claude-code / opus-5.5
Plan IDs: INF-013

## Summary
Turned off Vercel Git deployments for both web projects via vercel.json, after repeated failed deploys and preview access blocks.

## Files touched
- web/app/vercel.json, web/marketing/vercel.json: git.deploymentEnabled false

## Decisions
- Founder decision (Eldon, 2026-11-19): stop the Vercel story for now. Previews are paused; view apps with the local dev server. ADR-0018 viewability: previews return with INF-013 and hosting (INF-001).

## Tokens or cost
Small.

## Next step
Eldon: also disconnect the Git integration in the Vercel dashboard (Settings, Git) so no deploys or checks run. Re-enable by removing the two vercel.json files.
