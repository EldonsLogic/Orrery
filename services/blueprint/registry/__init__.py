"""Component registry (BPL-010): admission rules and queries over component manifests.

Standard library plus jsonschema. Needs `services/blueprint` on the import path (it reuses `validator.semver`).
"""
from .admission import admit
from .compat import CompatResult, check_compatibility
from .issues import Issue
from .registry import Registry
from .store import MAX_FILE_BYTES, DirectoryStore, ManifestStore, RawManifest

__all__ = ["Registry", "Issue", "admit", "CompatResult", "check_compatibility", "DirectoryStore",
           "ManifestStore", "RawManifest", "MAX_FILE_BYTES"]
