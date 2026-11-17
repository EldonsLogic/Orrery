"""What counts as an element, as data (BPL-022).

Source: docs/strategy/autonomy-metrics.md names "entities, fields, workflows, roles, reports, print formats,
integrations". The unit of count is one keyed object in a Blueprint collection (contract 1, v0.1.0), addressed by
a keyed RFC 6901 pointer (the same addressing bpdiff uses): `/entities/customer`, `/entities/customer/fields/name`,
`/roles/admin`. Child elements are not part of their parent's content: an entity's content is the entity without
its `fields` array, so a hand-edited field never turns its entity into a manual element. Approvals, locations,
components, branding, compliance and i18n are not elements (not in the list of the definition).

`print_format` has no collection in contract 1 v0.1.0, so it always counts 0 until the contract adds one; it is
listed so the breakdown shows the kind. Add a kind by adding a row here.
"""
from __future__ import annotations

from typing import NamedTuple


class ElementKind(NamedTuple):
    name: str
    parent: str | None      # collection of the parent element ("entities" for fields), None for top level
    collection: str         # top-level collection, or the array name inside the parent
    in_schema: bool = True


ELEMENT_KINDS: tuple[ElementKind, ...] = (
    ElementKind("entity", None, "entities"),
    ElementKind("field", "entities", "fields"),
    ElementKind("workflow", None, "workflows"),
    ElementKind("role", None, "roles"),
    ElementKind("report", None, "reports"),
    ElementKind("print_format", None, "printFormats", in_schema=False),
    ElementKind("integration", None, "integrations"),
)
