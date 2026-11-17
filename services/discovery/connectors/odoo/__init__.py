"""Odoo extractor (DSC-012), tier 1 official API, read-only. See services/discovery/README.md."""
from .connector import OdooConnector, register
from .errors import (ModelUnavailable, Odo001MethodNotAllowed, Odo002WriteRefused, Odo003ModelNotAllowed,
                     Odo004BadCall, Odo005SecretLike, Odo006BadRequest, Odo007BadConfig,
                     Odo008TransportFailure, Odo009MalformedResponse, OdooRefusal)
from .mapping import DEFAULT_MODELS, MAPPING, TYPE_MAP
from .transport import MAX_PAGE_SIZE, READ_METHODS, ReadOnlyGateway, Transport

__all__ = ["OdooConnector", "register", "OdooRefusal", "ModelUnavailable", "Odo001MethodNotAllowed",
           "Odo002WriteRefused", "Odo003ModelNotAllowed", "Odo004BadCall", "Odo005SecretLike",
           "Odo006BadRequest", "Odo007BadConfig", "Odo008TransportFailure", "Odo009MalformedResponse",
           "DEFAULT_MODELS", "MAPPING", "TYPE_MAP", "MAX_PAGE_SIZE", "READ_METHODS", "ReadOnlyGateway",
           "Transport"]
