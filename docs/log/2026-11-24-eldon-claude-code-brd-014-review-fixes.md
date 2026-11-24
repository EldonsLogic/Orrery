# Session log: brd-014-review-fixes

Date: 2026-11-24
Author: eldon
Tool and model: claude-code (Opus-class subagent)
Plan IDs: BRD-014

## Summary
Fixed the partner's review of #298 (BRD-014 part 1) at 658df11: provenance of the logo kit, Cairo in the licence register, reproducible icon rasters, the tenant preview mark and a stale path.

## Files touched
- docs/brand/tools/PROVENANCE.md: author and licence of the kit code (founder answer of 2026-11-24: Seshna founders with AI assistance, repo licence, only Cairo is third party).
- docs/legal/licence-register.md: Cairo row (google/fonts a2c83dae, OFL 1.1, build-time input for the wordmark and the heading font, not shipped); Alexandria row marked retired.
- docs/brand/tools/build_icons.py: PyMuPDF replaced by a stdlib rasteriser and a fixed-Huffman deflate, so PNG bytes no longer depend on MuPDF or zlib builds; `--check` mode. docs/brand/logo/png/* regenerated with it.
- docs/brand/tools/build_tenant_preview.py and preview-tenant-themes.html: chat avatar is the Nuqta S mark read from logo/mark-primary.svg.
- docs/brand/11-v1.1-additions.md, README.md: no reference to the deleted logo/proposed/; documented raster command.

## Checks
`build_icons.py --check` byte-identical under CPython 3.12.13 (uv) and the system CPython 3.9 on macOS arm64; every PNG decodes with zlib and MuPDF 1.28.6 to the same pixels. build_brand_assets --check, check_contrast, check_proposed, both tenant suites, 29 asset tests, check_docs, check_repo_hygiene, scan_secrets: pass. Not verified on Linux: arc points use libm cos/sin, so a last-bit difference there could in principle change a pixel.

## Decisions
- Rasters drop PyMuPDF for a stdlib renderer: pinning PyMuPDF 2.1 did not reproduce across machines (the reviewer saw 10 of 43 mismatches with the same version).

## Tokens or cost
Unknown.

## Next step
- Re-review of #298 by the partner; then part 2 (`brd-014-seshna-web`).
