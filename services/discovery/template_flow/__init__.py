"""Template-first discovery flow (DSC-004). See README.md."""
from .errors import FlowError
from .flow import Revision, TemplateFlow, digest
from .summary import load_registry

__all__ = ["TemplateFlow", "Revision", "FlowError", "digest", "load_registry"]
