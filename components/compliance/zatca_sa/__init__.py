"""
ZATCA Phase 1 E-Invoicing Component for Saudi Arabia.
Validates invoices, checks the engine's totals and generates the 5-tag TLV QR code.
It never computes tax (ADR-0031). Not yet verified against the ZATCA sandbox.
"""

from .phase1 import (
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
