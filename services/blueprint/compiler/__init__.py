"""Blueprint compiler (BPL-004): Blueprint + component registry + engine mapping -> compiled artifact.

Contracts: compiled-artifact.schema.json 0.1.0, engine-adapter.md 0.1.2 section 9, engine-mapping.schema.json 0.1.0.
Deterministic and pure. It emits configuration only: no ledger, tax, e-invoice or payroll figure, rate or rule is
computed or chosen here; every value in a step is copied verbatim from the Blueprint (ADR-0030, ADR-0033).

    from compiler import compile_blueprint, plan_view
    result = compile_blueprint(blueprint, registry, mapping, environment="sandbox")
    result.ok, result.artifact, result.errors

Open questions (conservative reading taken; to move to docs/open-questions.md):
1. Initial build source diff. The contract compiles from diff(base, target), but an initial build has no base.
   The compiler diffs an empty skeleton (same top-level containers, no content) to the target with bpdiff, takes
   sourceOps, skippedOps and risk counts from that diff, and sets diffHash null as the schema requires.
2. settings.set uniqueness. x-validator-rules say no two steps share (kind, pointer), but every company,
   compliance and i18n property is its own settings.set on the section pointer ("/company"), as the fake adapter's
   test kit stand-in does. The property breaks the sort tie. Contract needs either a per-property pointer or an
   exemption for settings.set.
3. i18n.labelOverrides. Contract 9.3 names only i18n.defaultLocale (settings.set) and the glossary (skipped).
   labelOverrides is compiled as settings.set, matching the fake's settings_intl exported properties.
4. Adapter id. The BPL-005 fixture and the golden mapping target adapter "change_engine"; the fake adapter and
   the sample artifacts use the engine's name (contract 16.12). The compiler passes meta.engineTarget through.
5. Phase order versus references. Contract 9.4 says additions run before their users, but entity.add (phase 4)
   names its workflow (phase 8), workflow transitions name approvals (phase 9), and entities and locations reference
   each other within one phase. plan_view reports these as forwardRefs; the adapter must resolve them.
6. The artifact has no field for the engine mapping id or version, so two different mappings that both pass give
   the same artifact (compiler identity rule in the schema). Record the mapping in the artifact?
7. Draft mappings. A draft mapping is accepted only for sandbox and only when its versionSet equals the
   Blueprint's or is marked UNVERIFIED; production needs a verified mapping with the same versionSet.
8. Valuation method and rounding (ADR-0033) have no field in the Blueprint or artifact 0.1.0; provisioning
   (ERP-003) sets them. The compiler passes field precision through and refuses a mapping whose computed-field
   precision differs from the Blueprint's. The rounding mode is not carried in the artifact.
9. Eligibility. The highest version in the Blueprint's range is resolved, then refused if not eligible for the
   environment (no silent fallback to a lower eligible version). A registry with any admission error refuses.
10. touchesLedgerOrTax counts components with certification.touchesLedgerOrTax or kind "rigid", and entities
   bound to them. Fields, workflows and reports on those entities are not counted separately.
11. Post-conditions use exists, count_equals and order_equals only: exportedProperties lists are open (16.3), so
   property_equals could fail on a correct site. Approval steps and report metrics are not order-checked because
   they are not keyed by id.
12. Scope. Only the initial build (base null, no inverse) is compiled. Incremental compiles (base to target with an
   embedded inverse, as in the samples) need their own plan row or a scope decision.
13. Environment. The Blueprint has no target environment field; the caller passes it. The CLI defaults to
   production, which fails closed for draft mappings and below-certified components.
"""
from .artifact import COMPILER, content_hash, to_bytes
from .core import compile_blueprint
from .plan import plan_view
from .result import CompileResult, Issue

compile = compile_blueprint  # noqa: A001  (the name in the plan row; compile_blueprint avoids the builtin)

__all__ = ["compile_blueprint", "compile", "plan_view", "CompileResult", "Issue", "COMPILER", "content_hash", "to_bytes"]
