"""Customer-facing API edge (PLT-024): path policy, allow-listed projection, header filtering, engine error mapping."""
from .errors import ERROR_CODES, ErrorResult, error_body, map_engine_error
from .gateway import Gateway, GatewayRequest, GatewayResponse, Route, UpstreamRequest, UpstreamResponse
from .headers import SESSION_COOKIE
from .markers import contains_engine_marker, contains_engine_structure
from .paths import normalise_path
from .projection import Field

__all__ = [
    "ERROR_CODES", "ErrorResult", "Field", "Gateway", "GatewayRequest", "GatewayResponse", "Route", "SESSION_COOKIE",
    "UpstreamRequest", "UpstreamResponse", "contains_engine_marker", "contains_engine_structure", "error_body",
    "map_engine_error", "normalise_path",
]
