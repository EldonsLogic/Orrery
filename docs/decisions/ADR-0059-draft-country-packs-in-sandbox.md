# ADR-0059: Draft country packs may run in sandbox and test (synthetic data only)

Status: Accepted
Owner: eldon
Approved by: Eldon, answering for both founders, 2026-11-22 (Q-560 / Q-292)

Plan ID: GOV-062.

## Context
- [ADR-0034](ADR-0034-reviewed-level-needs-a-named-reviewer.md) sets the component production boundary: `draft` is never eligible in any environment, and a component that touches the ledger or tax may wait at `tested` in sandbox but `draft` is "still refused for it" (ADR-0034 lines 12 and 14).
- A country pack is a component (`componentId` `country.<code>`, [country-pack-framework.md](../compliance/country-pack-framework.md) line 25) and carries locked tax, e-invoicing and payroll fields.
- The country pack loader already accepts `draft` packs outside production: its go-live gate returns early for any environment other than `production` (`components/compliance/country_pack/loader.py` lines 229-230; environments `sandbox`, `test`, `production` at line 24). The framework doc says so (country-pack-framework.md line 67). So code and ADR-0034 disagree.
- The Blueprint registry is not involved: `Registry._ELIGIBLE_LEVELS` (`services/blueprint/registry/registry.py` lines 95-98) gates only `blueprint.components[]`, not `compliance.countryPack` (country-pack-framework.md line 72).
- Eldon answered Q-560 on 2026-11-22 for both founders ([open-questions.md](../open-questions.md) Q-560): (1) production may use official sources or trusted adviser sources (for example a Big Four firm) once a qualified accountant has signed off; (2) a pack becomes `certified` when a named accountant for that market signs off and one founder approves; (3) sandbox may keep accepting `draft` packs, synthetic data only, and ADR-0034 needs a superseding note; (4) a pack's `status` must match the component manifest's `certification.level` and name the reviewer before the loader trusts it.

## Decision
1. **Sandbox and test exception (point 3).** A country pack at `draft` (or `tested`, `reviewed`, with `secondary` or `unverified` evidence) may be loaded in the `sandbox` and `test` environments. Those environments hold synthetic data only (AGENTS.md, Branches and PRs: "Dev hosts get synthetic data only"). This matches the loader as it stands; no code change is needed for this point.
2. **Narrow scope.** The exception covers country packs only, and only `sandbox` and `test`. It does not change:
   - the production boundary: in production a pack must be `certified` or `regulated`, `verified_official`, and not `testOnly` (loader.py lines 233-238);
   - ADR-0034 for every other component, including other ledger or tax components, which stay at `tested` or above in sandbox;
   - the Blueprint registry or the compiler's component gate;
   - the `testOnly` / `allow_test_packs` rule (country-pack-framework.md line 68).
3. **Policy the loader must follow next (points 1, 2, 4).** Recorded here so the next loader change has a fixed target. None is in force in code yet; until each lands, the loader keeps its current fail-closed behaviour, including refusing `secondary` evidence in production (loader.py lines 26-27).
   - **Adviser sources.** Production may accept `secondary` evidence from a trusted adviser source (for example a Big Four firm) only once a named qualified accountant for that market has signed off and the sign-off is recorded. A CMP row in the partner's lane implements this.
   - **Who certifies.** A pack becomes `certified` only when a named accountant for that market signs off and one founder approves. A CMP row in the partner's lane implements this.
   - **Status must match the manifest.** The loader trusts a pack's `status` only if it equals the component manifest's `certification.level` for that pack and the manifest names the reviewer (`reviewedBy`, ADR-0034 line 11); otherwise it refuses in production. A CMP row in the partner's lane implements this.

## Alternatives rejected
- **Refuse `draft` packs in sandbox too, matching ADR-0034 literally.** Packs are research-stage for most markets (Q-202 for Qatar VAT); refusing them would block tests and demos on synthetic data and gain no safety, because production stays fail closed.
- **Supersede ADR-0034 for all components.** Wider than the answer; other rigid-zone components keep the `tested` floor.
- **Write the full Q-560 policy into the loader in this ADR's PR.** The loader is in the partner's lane (CMP-034); this ADR records the policy and leaves the implementation to that lane.

## Consequences
- Code, the framework doc and the ADRs agree on sandbox behaviour for country packs.
- A production consumer must still call the loader with `environment="production"` (the default); this ADR does not add a gate to the compiler.
- Follow-ups: the three points in Decision item 3, each a CMP row in the partner's lane. Q-560 can be marked applied for point 3 once this ADR lands.

## Supersedes
[ADR-0034](ADR-0034-reviewed-level-needs-a-named-reviewer.md), in part: only the rule that `draft` is never eligible and is refused for a ledger or tax component (ADR-0034 lines 12 and 14), and only for country packs in the `sandbox` and `test` environments. Every other part of ADR-0034 stands, including its production boundary.
