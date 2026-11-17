"""
Engine compliance module for Saudi ZATCA e-invoicing.
"""

import importlib.util
import os
from pathlib import Path
import sys


def _ensure_components_on_path() -> None:
    """Locate the platform components root when running inside a standalone Frappe bench."""
    try:
        if importlib.util.find_spec("components.compliance.zatca_sa.phase1") is not None:
            return
    except ModuleNotFoundError:
        pass

    candidates = []
    env_root = os.environ.get("PLATFORM_COMPONENTS_ROOT")
    if env_root:
        candidates.append(Path(env_root))
    # Bench virtualenv layout: <bench_root>/env/bin/python
    exe_resolved = Path(sys.executable).resolve()
    if len(exe_resolved.parents) > 2:
        candidates.append(exe_resolved.parents[2])
    candidates.append(Path.cwd())
    # Repo layout fallback: <repo>/apps/engine/change_engine/change_engine/compliance/__init__.py
    resolved = Path(__file__).resolve()
    if len(resolved.parents) > 5:
        candidates.append(resolved.parents[5])

    for root in candidates:
        if (root / "components" / "compliance" / "zatca_sa" / "phase1.py").is_file():
            root_str = str(root)
            if root_str not in sys.path:
                sys.path.append(root_str)
            return


_ensure_components_on_path()

from components.compliance.zatca_sa.phase1 import (  # noqa: E402
    ZatcaInvoice,
    ZatcaParty,
    ZatcaAddress,
    ZatcaLineItem,
    ZatcaTaxTotal,
    encode_phase1_tlv,
    decode_phase1_tlv,
    generate_phase1_qr,
    validate_phase1_invoice,
    generate_phase1_invoice,
    ZatcaValidationError,
)

__all__ = [
    "ZatcaInvoice",
    "ZatcaParty",
    "ZatcaAddress",
    "ZatcaLineItem",
    "ZatcaTaxTotal",
    "encode_phase1_tlv",
    "decode_phase1_tlv",
    "generate_phase1_qr",
    "validate_phase1_invoice",
    "generate_phase1_invoice",
    "ZatcaValidationError",
]
