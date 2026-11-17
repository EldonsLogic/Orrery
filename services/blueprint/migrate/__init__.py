"""Blueprint schema migration (BPL-021). Pure, deterministic, stdlib only, fail closed.

    from migrate import migrate, register
    r = migrate(blueprint, target_version=None)       # default: the latest registered version
    r.ok, r.blueprint, r.steps, r.errors              # steps: StepRecord(from_version, to_version, changes)

Open questions are in docs/open-questions.md (Q-86 onward). Design: docs/architecture/blueprint-versioning.md.
"""
from .core import (CURRENT_SCHEMA_VERSION, Issue, MigrationResult, Registry, StepRecord, REGISTRY, migrate,
                   register)

__all__ = ["migrate", "register", "Registry", "REGISTRY", "MigrationResult", "StepRecord", "Issue",
           "CURRENT_SCHEMA_VERSION"]
