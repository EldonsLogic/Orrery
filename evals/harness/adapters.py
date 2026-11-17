"""Adapter protocol and offline test adapters.

A real model adapter (not built; needs the model gateway, PLT-* rows) MUST call the model only
through our gateway, and MUST read endpoint and credentials from the environment, never from the
repo. No provider SDK lives in this package. Register it in ADAPTERS under a new name.
"""
import json
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


class ReplayAdapter:
    """Scores answers a model already gave, read from a JSONL file (one object per line with `id` and the
    Response fields). No model is called here; a missing or malformed line scores as no response. Used by
    the bake-off (QA-003): `--adapter replay:<path>`."""

    def __init__(self, path: str):
        self.name = f"replay:{path}"
        self._by_id: dict = {}
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if isinstance(obj, dict) and isinstance(obj.get("id"), str):
                    self._by_id[obj["id"]] = obj

    def respond(self, record: dict) -> Response:
        o = self._by_id.get(record["id"])
        if not o:
            return Response()
        args = o.get("args") if isinstance(o.get("args"), dict) else {}
        norm = o.get("normalized") if isinstance(o.get("normalized"), dict) else {}
        text = o.get("text") if isinstance(o.get("text"), str) else ""
        return Response(kind=o.get("kind"), intent=o.get("intent"), tool=o.get("tool"), args=args,
                        normalized=norm, text=text)


ADAPTERS = {a.name: a for a in (EchoExpectedAdapter(), NullAdapter())}


def get_adapter(name: str):
    if name.startswith("replay:"):
        return ReplayAdapter(name[len("replay:"):])
    if name not in ADAPTERS:
        raise KeyError(f"unknown adapter '{name}'; available: {', '.join(sorted(ADAPTERS))}")
    return ADAPTERS[name]
