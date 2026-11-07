"""Adapter protocol and offline test adapters.

A real model adapter (not built; needs the model gateway, PLT-* rows) MUST call the model only
through our gateway, and MUST read endpoint and credentials from the environment, never from the
repo. No provider SDK lives in this package. Register it in ADAPTERS under a new name.
"""
from dataclasses import dataclass, field
from typing import Optional, Protocol


@dataclass
class Response:
    """What a model produced for one record. `kind` is the response type (intent, tool_call,
    answer, clarify, refusal); None means no usable response."""
    kind: Optional[str] = None
    intent: Optional[str] = None
    tool: Optional[str] = None
    args: dict = field(default_factory=dict)
    normalized: dict = field(default_factory=dict)
    text: str = ""


class Adapter(Protocol):
    name: str

    def respond(self, record: dict) -> Response: ...


class EchoExpectedAdapter:
    """Test oracle: returns the expected value. Proves scorers give 100%."""
    name = "echo_expected"

    def respond(self, record: dict) -> Response:
        e = record["expected"]
        text = " ".join(e.get("must_include", [])) if e["type"] == "answer" else ""
        return Response(kind=e["type"], intent=e.get("intent"), tool=e.get("tool"),
                        args=dict(e.get("args", {})), normalized=dict(e.get("normalized", {})), text=text)


class NullAdapter:
    """Returns nothing. Proves 0%."""
    name = "null"

    def respond(self, record: dict) -> Response:
        return Response()


ADAPTERS = {a.name: a for a in (EchoExpectedAdapter(), NullAdapter())}


def get_adapter(name: str):
    if name not in ADAPTERS:
        raise KeyError(f"unknown adapter '{name}'; available: {', '.join(sorted(ADAPTERS))}")
    return ADAPTERS[name]
