"""Engine selection hook. STUDIO_ENGINE=fake (default) uses the in-memory fake adapter (BPL-025). STUDIO_ENGINE=module:factory
names a zero-argument factory returning an AdapterHarness (services/blueprint/adapter/README.md, contract section 15.1), so
the real adapter (BPL-012) can be plugged in later. Anything that cannot be imported or built refuses to start."""
from __future__ import annotations

import importlib
import os
import re
from dataclasses import dataclass
from typing import Callable

from . import _paths  # noqa: F401  (import path setup)
from adapter.harness import AdapterHarness, FakeHarness  # type: ignore  # noqa: E402

ENV_VAR = "STUDIO_ENGINE"
_SPEC = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*:[A-Za-z_][A-Za-z0-9_]*")
# The fake declares the 'attachment' value type unsupported (services/blueprint/tests/compiler/test_cmp_props.py, round trip).
FAKE_UNSUPPORTED_FIELD_TYPES = ("attachment",)


class EngineUnavailable(RuntimeError):
    """The configured engine cannot be used; the server must not start."""


@dataclass(frozen=True)
class Engine:
    kind: str                                  # "fake" or "plugged"
    factory: Callable[[], AdapterHarness]
    unsupported_field_types: tuple

    def new_harness(self) -> AdapterHarness:
        h = self.factory()
        if not isinstance(h, AdapterHarness):
            raise EngineUnavailable("the engine factory did not return an AdapterHarness")
        return h

    def badge(self) -> dict:
        """What the UI shows. Never the engine's own name (ADR-0016)."""
        return {"kind": self.kind, "labelKey": "engine." + self.kind}


def load_engine(spec: str | None = None) -> Engine:
    spec = (os.environ.get(ENV_VAR, "") if spec is None else spec).strip() or "fake"
    if spec == "fake":
        return Engine("fake", FakeHarness, FAKE_UNSUPPORTED_FIELD_TYPES)
    if not _SPEC.fullmatch(spec):
        raise EngineUnavailable(f"{ENV_VAR} must be 'fake' or 'module:factory'")
    module, _, name = spec.partition(":")
    try:
        factory = getattr(importlib.import_module(module), name)
    except (ImportError, AttributeError) as exc:
        raise EngineUnavailable(f"{ENV_VAR}={spec} cannot be imported ({type(exc).__name__})") from None
    if not callable(factory):
        raise EngineUnavailable(f"{ENV_VAR}={spec} is not callable")
    engine = Engine("plugged", factory, ())
    try:
        engine.new_harness()
    except EngineUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001  (any failure to build the adapter refuses to start)
        raise EngineUnavailable(f"{ENV_VAR}={spec} could not be built ({type(exc).__name__})") from None
    return engine
