"""Row schema of the exceptions register (columns of docs/runbooks/exceptions-register.md).

The store adds `id` (sequential per file). A caller supplies the other columns; `corrects` is optional and, when
present, is the id of an earlier row this row corrects.
"""
from __future__ import annotations

CLASSES = ("missing_component", "component_gap", "mapping_gap", "client_specific", "error_in_draft")

REQUIRED = ("date", "tenant", "blueprint_rev", "element_pointer", "edited_by_hand", "reason", "class",
            "proposed_automation", "owner")
OPTIONAL = ("follow_up", "corrects")
STORED = ("id",)
ALL_COLUMNS = REQUIRED + OPTIONAL + STORED

ID_COLUMNS = ("tenant", "blueprint_rev", "owner")   # short identifiers, pattern-checked
TEXT_COLUMNS = {                                     # free text -> max characters
    "edited_by_hand": 300, "reason": 500, "proposed_automation": 500, "follow_up": 300,
}
MAX_POINTER = 300
MAX_ID = 64
MAX_LINE_BYTES = 4096
