"""services/studio: a local, live Studio that runs the merged code end to end on synthetic data (no recorded output).

    python3 -m services.studio            # from the repo root; http://127.0.0.1:8765/

Pieces reused, never copied: compile_blueprint (services/blueprint/compiler), the adapter harness and its fake
(services/blueprint/adapter), resolve_tokens (services/blueprint/tokens), the synthetic dataset loader (services/datasets)
and the Phase 1 TLV encoder (components/compliance/zatca_sa/phase1.py). In-memory state only; nothing is written to disk.

Open questions (conservative reading taken; to move to docs/open-questions.md by a founder lane):
1. Rollback (BPL-039). The first apply is an initial build (inverse null), which the adapter contract refuses to roll
   back (rollback_not_possible / no_inverse). Every later apply is an incremental compile against the engine-form
   Blueprint that was last applied (same re-targeting and dropped field types, so the base hash matches the site), with
   an embedded inverse; /api/rollback rolls the latest one back, and the history moves back one revision. A change with
   an irreversible step is refused as a whole (irreversible_step), site unchanged. /api/compile reports one
   artifact-level "reversible" answer before apply. /api/apply also takes {"failAtStep": N} to show the automatic
   undo: the fake fails that step and compensates (export hash back to the pre-apply hash). With no edit since the
   last apply, /api/compile reports "unchanged" and /api/apply refuses with STUDIO-NO-CHANGES.
2. Two artifact ids. The Compile tab shows the artifact for the Blueprint as written (adapter "change_engine"). Apply
   re-targets a copy to the engine's adapter id (compiler question 4) and, for the fake only, drops 'attachment'
   fields (the fake declares that value type unsupported). Its artifact id and step count can differ; both are shown.
3. Environment. Compiles run as sandbox: the fixture's manifests are 'tested', which production refuses (CMP-COMP-003).
4. Approvals. Apply grants the approvals the plan asks for (changeApproved, gateApproved, teamReviewed) with synthetic
   ids, as the conformance test kit does. A real Studio needs a human approval step.
5. QR inputs. Tag 3 (timestamp) is the dataset's invoice_date (a date, no time), passed verbatim: the dataset has no
   issue time and nothing is invented. Tag 1 is the Arabic legal name. The five-tag Phase 1 layout is Saudi; for the
   UAE, Egypt and Qatar it is shown only to exercise the encoder, not as a legal requirement there.
6. Engine name guard. Any JSON response that contains the engine's name is replaced by STUDIO-ENGINE-NAME (500), so a
   label a user types that happens to contain that word is refused instead of shown.
7. Lanes. services/studio/ is not listed in scripts/lanes.json (shared by default); a founder should assign it.
8. A plugged engine (STUDIO_ENGINE=module:factory) drops no fields up front; its unsupported value types are not
   discoverable through capabilities (contract 0.1.2 has no such field). When its preview rejects, apply retries once
   without 'attachment' fields, and later incremental applies keep that skip (question 1).
"""
