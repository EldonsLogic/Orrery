# Country packs root

This folder, `components/compliance/country_pack/packs/`, is the packs root for real country packs. Pass it as `packs_dir` to `load_country_pack` and `resolve_country_pack` in [../loader.py](../loader.py). The synthetic fixture in `../tests/sample_packs/` is test data only and is never a packs root.

Layout (see [country-pack-framework.md](../../../../docs/compliance/country-pack-framework.md)):

```text
packs/
  <country_code_lower>/   # sa | ae | eg | qa
    <semver>/             # e.g. 0.1.0
      pack.json           # validated against ../pack.schema.json
      manifest.json       # component manifest (contracts/component.manifest.schema.json)
      evidence.json       # source, access date and evidence label per fact; pending refs; Arabic label review state
```

Packs are rigid-zone data (ADR-0031, Tier 3): declarative metadata and references only, never tax, ledger or e-invoice maths. A real pack has `testOnly: false`. `evidence.json` exists because the pack schema has no per-fact evidence field. Tests: `../tests/test_pack_sa_ae.py`.
