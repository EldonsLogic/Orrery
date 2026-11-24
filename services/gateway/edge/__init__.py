"""Customer-facing API edge (PLT-024): path policy, header/cookie filtering, engine error mapping."""
from .errors import ERROR_CODES, ErrorResult, error_body, map_engine_error
from .gateway import Gateway, GatewayRequest, GatewayResponse, UpstreamRequest, UpstreamResponse
from .headers import SESSION_COOKIE
from .markers import contains_engine_marker
from .paths import normalise_path

__all__ = [
    "ERROR_CODES", "ErrorResult", "Gateway", "GatewayRequest", "GatewayResponse", "SESSION_COOKIE",
    "UpstreamRequest", "UpstreamResponse", "contains_engine_marker", "error_body", "map_engine_error",
    "normalise_path",
]
