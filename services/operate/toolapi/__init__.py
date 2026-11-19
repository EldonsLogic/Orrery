"""Tool API generator (OPR-003): validated Blueprint -> typed, per-tenant tool definitions.

Contract: contracts/tool-api.md 0.3.0. Pure, deterministic, no I/O. Refusals carry `TAPI-` codes and fail closed.

    from toolapi import generate_tool_api, check_tool_api
    result = generate_tool_api(blueprint)        # result.ok, result.tools, result.content_hash, result.errors
    issues = check_tool_api(result.definition_set())

Every rule that decides a risk class, an effect or a verb label lives in `policy.py` as data.
"""
from .check import check_tool_api
from .errors import build_error, load_catalog, render_message, validate_catalog
from .generate import generate_tool_api
from .result import Issue, ToolApiResult, to_bytes

__all__ = ["generate_tool_api", "check_tool_api", "ToolApiResult", "Issue", "to_bytes",
           "load_catalog", "validate_catalog", "build_error", "render_message"]
