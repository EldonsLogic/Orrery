# Country packs root

This folder, `components/compliance/country_pack/packs/`, is the packs root for real country packs. Pass it as `packs_dir` to `load_country_pack` and `resolve_country_pack` in [../loader.py](../loader.py). The synthetic fixture in `../tests/sample_packs/` is test data only and is never a packs root.

Layout (see [country-pack-framework.md](../../../../docs/compliance/country-pack-framework.md)):

```text
packs/
  <country_code_lower>/   # sa | ae | eg | qa
    <semver>/             # e.g. 0.1.0
      pack.json           # validated against ../pack.schema.json
      manifest.json       # component manifest (contracts/component.manifest.schema.json)
      evidence.json       # source, access date (or "read": false) and evidence label per fact; pending refs; Arabic label review state
      strings.json        # optional: i18n labels, only when manifest.json names it in i18n.stringsFile
```

Packs are rigid-zone data (ADR-0031, Tier 3): declarative metadata and references only, never tax, ledger or e-invoice maths. A real pack has `testOnly: false`. `evidence.json` exists because the pack schema has no per-fact evidence field. Every pack uses the same files: no `SOURCES.md` or README source tables beside a pack; sources live only in `evidence.json`. Tests: `../tests/test_country_packs.py` runs the shared checks over every pack here (evidence coverage, labels and access dates, `requires`, status, `provides`, no rate-like digits, Arabic review state). Each pack also has its own test module in `../tests/`, named `test_pack_<cc>.py` or similar (one module may cover several packs), listed in that pack's `manifest.json` under `tests`.
