# Session log: sec-007-dependency-scanning

Date: 2026-11-17
Author: eldon
Tool and model: claude-code / sonnet-5.5
Plan IDs: SEC-007

## Summary
Added dependency and SBOM scanning: Dependabot for pip and npm, a CI dependency-audit job (pip-audit, pinned) that publishes a CycloneDX SBOM, and a short baseline section.

## Files touched
- .github/dependabot.yml, .github/workflows/ci.yml: ecosystems and dependency-audit job
- docs/security/security-baseline.md: section; docs/PLAN.md: SEC-007 done

## Decisions
- None. Hash-pinned installs and image scanning left open.

## Tokens or cost
Unknown or approximate, if known.

## Next step
Exact pins with hashes for evals requirements; image scanning when images exist.
