"""Plain types of the intent router. Closed label sets; the decision carries codes only, never free text."""
from __future__ import annotations

from dataclasses import dataclass, field

MODES = ("discover", "ask", "act", "change")
PRIVILEGED = frozenset({"act", "change"})  # modes that lead to writes; they need rules support and confirmation
SAFE_MODE = "ask"                           # the least privileged mode: uncertainty and disagreement land here
RISK_ORDER = ("R0", "R1", "R2", "R3", "R4")  # same order as toolapi.policy.RISK_ORDER (tested equal)
_RANK = {r: i for i, r in enumerate(RISK_ORDER)}
MODE_RISK_FLOOR = {"discover": "R0", "ask": "R0", "act": "R1", "change": "R2"}  # placeholder, see Q-252
CONFIDENCE = ("low", "medium", "high")
ABSTAIN = "abstain"
CLASSIFIER_LABELS = MODES + (ABSTAIN,)

# Every reason code the router can emit. Tests check emitted codes are a subset.
REASONS = frozenset({
    "slash_command", "confirmation_of_pending", "interrogative", "read_verb", "imperative_action", "desire_action",
    "polite_request", "config_object", "business_object", "entity_match", "discovery_phrase", "mixed_intent",
    "no_signal", "meta_instruction", "data_ignored", "classifier_agree", "classifier_disagree", "classifier_abstain",
    "classifier_invalid", "classifier_error", "classifier_none", "classifier_rescue", "privileged_needs_rules",
    "act_unavailable", "pre_live_change_is_discovery", "needs_confirmation", "hint_raised_risk", "hint_invalid",
    "empty_input", "ambiguous_reference", "confirmation_without_pending",
})


def max_risk(*risks) -> str:
    """Highest valid class of the arguments; an invalid or missing value is skipped. Never lowers."""
    valid = [r for r in risks if r in _RANK]
    return max(valid, key=_RANK.__getitem__) if valid else "R0"


@dataclass(frozen=True)
class Pending:
    """A confirmation the host is waiting for (set by trusted host state, never by message text)."""
    mode: str  # act | change


@dataclass(frozen=True)
class RouteContext:
    """Trusted per-session facts from the host. `entity_names` come from the live Blueprint."""
    blueprint_live: bool = True
    entity_names: tuple = ()
    pending: Pending | None = None
    locale: str = "en"


@dataclass(frozen=True)
class RouteDecision:
    mode: str
    confidence: str                   # low | medium | high
    reasons: tuple                    # sorted reason codes
    abstain: bool = False             # True: no mode was established; mode is the safe one and `clarify_key` is set
    clarify_key: str | None = None    # i18n key of the clarifying question, rendered by the chat service
    requires_confirmation: bool = False
    risk_hint: str = "R0"             # never lower than the caller's hint or the mode floor
    explicit_command: bool = False
    rules_mode: str | None = None
    classifier_label: str | None = None
    data_items_ignored: int = 0
    intent_hint: str | None = None    # optional label from a metrics-side resolver; never used for authority
    extra: dict = field(default_factory=dict, compare=False)

    def __post_init__(self):
        assert self.mode in MODES and self.confidence in CONFIDENCE
        assert set(self.reasons) <= REASONS
