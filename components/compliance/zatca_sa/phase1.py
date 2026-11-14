"""
ZATCA Phase 1 E-Invoicing Generation and Validation.
Saudi Arabia E-Invoicing Regulation (Fatoora Phase 1).

Implements:
1. 5-tag TLV QR code encoding and decoding.
2. Mandatory invoice field validation per VAT Implementing Regulations (Art. 53)
   and ZATCA E-Invoicing Resolution (Annex 2).
3. Consistency checks on the totals the engine computed (ADR-0031: the engine is the only
   calculation authority; this module never computes tax and never substitutes its own figure).
4. Required references (preceding invoice, reason) on credit and debit notes. Nothing here
   enforces immutability; that belongs to the engine's ledger settings.

Status: implemented, not yet verified against the ZATCA sandbox or reviewed by an accountant.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone as dt_timezone
import re
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# KSA 15-digit VAT number format: begins with '3' and ends with '3'.
# UNVERIFIED: the rule is widely used but its official source is not yet cited here.
KSA_VAT_REGEX = re.compile(r"^3\d{13}3$")
DATE_REGEX = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_REGEX = re.compile(r"^\d{2}:\d{2}(:\d{2})?$")

# Fields a caller must supply; nothing is defaulted, because an invented value on a tax
# document is worse than a refusal.
REQUIRED_INVOICE_KEYS = ("invoice_id", "issue_date", "issue_time", "timezone", "invoice_type",
                         "transaction_type", "currency", "seller", "lines", "totals")
REQUIRED_LINE_KEYS = ("item_code", "description", "quantity", "unit_price", "vat_rate", "vat_category")
REQUIRED_TOTAL_KEYS = ("total_taxable_amount", "total_vat_amount", "grand_total")

ZERO = Decimal("0.00")
TWO_DECIMALS = Decimal("0.01")


class ZatcaValidationError(ValueError):
    """Raised when an invoice fails ZATCA Phase 1 compliance validation."""

    def __init__(self, message: str, errors: Optional[List[str]] = None):
        super().__init__(message)
        self.errors = errors or [message]


def to_decimal(val: Any) -> Decimal:
    """Convert an engine-supplied value to a finite Decimal without rounding it."""
    if isinstance(val, Decimal):
        dec = val
    elif isinstance(val, (int, str)):
        try:
            dec = Decimal(str(val))
        except InvalidOperation as exc:
            raise ZatcaValidationError(f"Amount '{val}' is not a number") from exc
    else:
        raise ZatcaValidationError(f"Amount must be a Decimal, int or string, not {type(val).__name__}")
    if not dec.is_finite():
        raise ZatcaValidationError(f"Amount '{val}' must be a finite number")
    return dec


def is_two_decimals(val: Decimal) -> bool:
    """True if the amount already has at most 2 decimal places (no rounding is applied here)."""
    return val == val.quantize(TWO_DECIMALS)


@dataclass
class ZatcaAddress:
    """Postal and street address within KSA."""
    street: str
    building_no: str
    postal_code: str
    city: str
    district: str
    country_code: str = "SA"

    def validate(self, party_type: str = "Party") -> List[str]:
        errors = []
        if not self.street or not self.street.strip():
            errors.append(f"{party_type} street is required")
        if not self.city or not self.city.strip():
            errors.append(f"{party_type} city is required")
        if not self.postal_code or not self.postal_code.strip():
            errors.append(f"{party_type} postal code is required")
        if self.country_code != "SA":
            errors.append(f"{party_type} country code must be 'SA' for domestic invoices")
        return errors


@dataclass
class ZatcaParty:
    """Seller or Buyer legal entity details."""
    name: str
    vat_number: Optional[str] = None
    address: Optional[ZatcaAddress] = None
    name_ar: Optional[str] = None
    cr_number: Optional[str] = None
    buyer_id_type: Optional[str] = None  # CRN, MOMRAH, MLSD, 700, NAT, PAS
    buyer_id_value: Optional[str] = None

    def validate(self, is_seller: bool = False, is_b2b_buyer: bool = False) -> List[str]:
        errors = []
        if not self.name or not self.name.strip():
            label = "Seller" if is_seller else "Buyer"
            errors.append(f"{label} legal name is required")

        if is_seller:
            if not self.vat_number or not self.vat_number.strip():
                errors.append("Seller VAT registration number is mandatory")
            elif not KSA_VAT_REGEX.match(self.vat_number.strip()):
                errors.append(
                    f"Seller VAT registration number '{self.vat_number}' is invalid. "
                    "Must be exactly 15 digits starting and ending with '3'."
                )
            if not self.address:
                errors.append("Seller address in KSA is mandatory")
            else:
                errors.extend(self.address.validate("Seller"))

        if is_b2b_buyer:
            if not self.address:
                errors.append("Buyer address is mandatory for standard (B2B) tax invoices")
            else:
                errors.extend(self.address.validate("Buyer"))
            if self.vat_number:
                if not KSA_VAT_REGEX.match(self.vat_number.strip()):
                    errors.append(
                        f"Buyer VAT registration number '{self.vat_number}' is invalid. "
                        "Must be exactly 15 digits starting and ending with '3'."
                    )

        return errors


@dataclass
class ZatcaLineItem:
    """Line item in a ZATCA invoice. Rates come from the engine (country pack), never from here."""
    item_code: str
    description: str
    quantity: Decimal
    unit_price: Decimal
    vat_rate: Optional[Decimal] = None
    discount: Decimal = ZERO
    vat_category: str = "S"  # S: Standard, Z: Zero-rated, E: Exempt, O: Out-of-scope
    exemption_reason_code: Optional[str] = None
    exemption_reason_text: Optional[str] = None

    def validate(self, line_index: int = 1) -> List[str]:
        errors = []
        if not self.description or not self.description.strip():
            errors.append(f"Line {line_index}: Item description is required")
        if self.quantity == ZERO:
            errors.append(f"Line {line_index}: Quantity cannot be zero")
        elif self.quantity < ZERO:
            errors.append(f"Line {line_index}: Quantity cannot be negative (a credit note is its own document type)")
        if self.unit_price < ZERO:
            errors.append(f"Line {line_index}: Unit price cannot be negative")
        if self.discount < ZERO:
            errors.append(f"Line {line_index}: Discount cannot be negative")
        if self.quantity > ZERO and self.discount > self.quantity * self.unit_price:
            errors.append(f"Line {line_index}: Discount cannot exceed line gross amount")

        # VAT category checks. The exact standard rate belongs to the country pack and the engine.
        if self.vat_rate is None:
            errors.append(f"Line {line_index}: VAT rate is required (supplied by the engine)")
        elif self.vat_category == "S":
            if self.vat_rate <= ZERO:
                errors.append(f"Line {line_index}: Standard rate category 'S' must have a VAT rate above 0")
        elif self.vat_category in ("Z", "E", "O"):
            if self.vat_rate != ZERO:
                errors.append(
                    f"Line {line_index}: Category '{self.vat_category}' must have VAT rate 0.00 (0%)"
                )
            if not self.exemption_reason_code and not self.exemption_reason_text:
                errors.append(
                    f"Line {line_index}: Category '{self.vat_category}' requires an exemption reason or code"
                )
        else:
            errors.append(f"Line {line_index}: Unsupported VAT category '{self.vat_category}'. Must be S, Z, E, or O.")

        return errors


@dataclass
class ZatcaTaxTotal:
    """Invoice totals exactly as the engine computed them (ADR-0031). Never computed here."""
    total_taxable_amount: Decimal
    total_vat_amount: Decimal
    grand_total: Decimal

    def validate(self) -> List[str]:
        """Compare the engine's figures with each other; fail closed, never correct them.

        The totals are deliberately not recomputed from the lines: the engine is the only
        calculation authority (ADR-0031), so a line-level check would be a second calculator.
        """
        errors = []
        figures = {
            "Total taxable amount": self.total_taxable_amount,
            "Total VAT amount": self.total_vat_amount,
            "Grand total": self.grand_total,
        }
        for label, val in figures.items():
            if val < ZERO:
                errors.append(f"{label} cannot be negative")
            if not is_two_decimals(val):
                errors.append(f"{label} '{val}' must already be rounded to 2 decimals by the engine")
        if self.total_taxable_amount + self.total_vat_amount != self.grand_total:
            errors.append(
                f"Engine totals disagree: taxable {self.total_taxable_amount} + VAT "
                f"{self.total_vat_amount} != grand total {self.grand_total}"
            )
        return errors


@dataclass
class ZatcaInvoice:
    """
    Representation of a ZATCA Phase 1 Invoice.
    Handles both Standard (B2B) and Simplified (B2C) tax invoices and notes.
    """
    invoice_id: str
    issue_date: str  # YYYY-MM-DD
    issue_time: str  # HH:MM:SS
    invoice_type: str  # "standard" or "simplified"
    timezone: str  # IANA name of the zone issue_date and issue_time are in, e.g. "Asia/Riyadh"
    transaction_type: str  # "tax_invoice", "simplified_tax_invoice", "credit_note", "debit_note"
    seller: ZatcaParty
    totals: Optional[ZatcaTaxTotal] = None
    lines: List[ZatcaLineItem] = field(default_factory=list)
    buyer: Optional[ZatcaParty] = None
    currency: str = "SAR"
    preceding_invoice_reference: Optional[str] = None
    amendment_reason: Optional[str] = None
    qr_code_tlv: Optional[str] = None

    def local_issue_datetime(self) -> Optional[datetime]:
        """The issue date and time as a real, zone-aware datetime, or None if invalid."""
        date_part = (self.issue_date or "").strip()
        time_part = (self.issue_time or "").strip()
        if not DATE_REGEX.match(date_part) or not TIME_REGEX.match(time_part):
            return None
        if len(time_part) == 5:
            time_part += ":00"
        try:
            zone = ZoneInfo((self.timezone or "").strip())
            naive = datetime.strptime(f"{date_part}T{time_part}", "%Y-%m-%dT%H:%M:%S")
        except (ZoneInfoNotFoundError, ValueError):
            return None
        return naive.replace(tzinfo=zone)

    def utc_timestamp(self) -> str:
        """QR tag 3: the issue time converted to UTC, as YYYY-MM-DDTHH:MM:SSZ."""
        local = self.local_issue_datetime()
        if local is None:
            raise ZatcaValidationError("Issue date, time or timezone is invalid")
        return local.astimezone(dt_timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    @property
    def is_standard(self) -> bool:
        return self.invoice_type.lower() == "standard"

    @property
    def is_simplified(self) -> bool:
        return self.invoice_type.lower() == "simplified"

    @property
    def is_adjustment_note(self) -> bool:
        return self.transaction_type in ("credit_note", "debit_note")

    def validate(self) -> List[str]:
        """Perform full validation against ZATCA Phase 1 regulations."""
        errors = []

        if not self.invoice_id or not self.invoice_id.strip():
            errors.append("Invoice identifier (sequential reference) is mandatory")

        if not self.issue_date or not DATE_REGEX.match(self.issue_date.strip()):
            errors.append(f"Issue date '{self.issue_date}' is invalid. Must be 'YYYY-MM-DD'.")

        if not self.issue_time or not TIME_REGEX.match(self.issue_time.strip()):
            errors.append(f"Issue time '{self.issue_time}' is invalid. Must be 'HH:MM:SS'.")

        if self.local_issue_datetime() is None and not errors:
            errors.append(
                f"Issue date '{self.issue_date}', time '{self.issue_time}' or timezone "
                f"'{self.timezone}' is not a real date, time and IANA zone."
            )

        if self.currency != "SAR":
            errors.append(f"Currency '{self.currency}' is invalid. Standard KSA currency is 'SAR'.")

        if self.invoice_type not in ("standard", "simplified"):
            errors.append(f"Invoice type '{self.invoice_type}' must be either 'standard' or 'simplified'.")

        if not self.seller:
            errors.append("Seller information is mandatory")
        else:
            errors.extend(self.seller.validate(is_seller=True))

        if self.is_standard:
            if not self.buyer:
                errors.append("Buyer information is mandatory for Standard (B2B) tax invoices")
            else:
                errors.extend(self.buyer.validate(is_b2b_buyer=True))

        if not self.totals:
            errors.append("Invoice totals from the engine are mandatory")
        else:
            errors.extend(self.totals.validate())

        if not self.lines:
            errors.append("Invoice must contain at least one line item")
        else:
            for idx, line in enumerate(self.lines, start=1):
                errors.extend(line.validate(idx))

        if self.is_adjustment_note:
            if not self.preceding_invoice_reference or not self.preceding_invoice_reference.strip():
                errors.append(
                    f"Preceding invoice reference is mandatory for {self.transaction_type} adjustment notes."
                )
            if not self.amendment_reason or not self.amendment_reason.strip():
                errors.append(
                    f"Amendment reason is mandatory for {self.transaction_type} adjustment notes."
                )

        return errors


def validate_phase1_invoice(invoice: ZatcaInvoice) -> List[str]:
    """
    Validate a ZatcaInvoice instance against ZATCA Phase 1 regulations.
    Returns an empty list if compliant, or a list of validation error strings.
    """
    return invoice.validate()


def encode_phase1_tlv(
    seller_name: str,
    vat_number: str,
    timestamp_iso: str,
    invoice_total_str: str,
    vat_total_str: str,
) -> str:
    """
    Encode the 5 mandatory ZATCA Phase 1 QR tags into binary TLV format and return Base64.

    Tag 1: Seller's Name (UTF-8)
    Tag 2: Seller's VAT Registration Number
    Tag 3: Time Stamp (ISO 8601 string)
    Tag 4: Invoice Total (with VAT, e.g. '115.00')
    Tag 5: VAT Total (e.g. '15.00')
    """
    tags = [
        (1, seller_name.strip()),
        (2, vat_number.strip()),
        (3, timestamp_iso.strip()),
        (4, invoice_total_str.strip()),
        (5, vat_total_str.strip()),
    ]

    tlv_buffer = bytearray()
    for tag_num, value_str in tags:
        val_bytes = value_str.encode("utf-8")
        val_len = len(val_bytes)
        if val_len > 255:
            raise ValueError(f"Tag {tag_num} value exceeds maximum single-byte length: {val_len} bytes")
        tlv_buffer.append(tag_num)
        tlv_buffer.append(val_len)
        tlv_buffer.extend(val_bytes)

    return base64.b64encode(tlv_buffer).decode("ascii")


def decode_phase1_tlv(b64_tlv_string: str) -> Dict[int, str]:
    """
    Decode a Base64-encoded ZATCA Phase 1 TLV string into a dictionary of {tag_id: value_str}.
    """
    try:
        raw_bytes = base64.b64decode(b64_tlv_string)
    except Exception as exc:
        raise ValueError(f"Invalid Base64 string for TLV decoding: {exc}") from exc

    results: Dict[int, str] = {}
    index = 0
    buffer_length = len(raw_bytes)

    while index < buffer_length:
        if index + 2 > buffer_length:
            raise ValueError("Truncated TLV header")
        tag = raw_bytes[index]
        length = raw_bytes[index + 1]
        val_start = index + 2
        val_end = val_start + length

        if val_end > buffer_length:
            raise ValueError(f"Truncated TLV value for tag {tag}: expected {length} bytes")

        val_bytes = raw_bytes[val_start:val_end]
        results[tag] = val_bytes.decode("utf-8")
        index = val_end

    return results


def generate_phase1_qr(invoice: ZatcaInvoice) -> str:
    """
    Generate the Base64-encoded Phase 1 TLV QR string for an invoice and assign it.
    Uses the engine's totals as given; refuses an invoice that fails validation.
    """
    errors = invoice.validate()
    if errors:
        raise ZatcaValidationError(
            f"ZATCA Phase 1 invoice validation failed with {len(errors)} error(s)", errors=errors
        )
    totals = invoice.totals

    # Time stamp: the local issue time converted to UTC, YYYY-MM-DDTHH:MM:SSZ
    timestamp_iso = invoice.utc_timestamp()

    # Prefer Arabic name if present, otherwise default name
    seller_name = (
        invoice.seller.name_ar.strip()
        if invoice.seller.name_ar and invoice.seller.name_ar.strip()
        else invoice.seller.name.strip()
    )

    qr_base64 = encode_phase1_tlv(
        seller_name=seller_name,
        vat_number=invoice.seller.vat_number or "",
        timestamp_iso=timestamp_iso,
        invoice_total_str=f"{totals.grand_total:.2f}",
        vat_total_str=f"{totals.total_vat_amount:.2f}",
    )

    invoice.qr_code_tlv = qr_base64
    return qr_base64


def generate_phase1_invoice(invoice_dict: Dict[str, Any]) -> ZatcaInvoice:
    """
    High-level factory function:
    1. Parses dictionary invoice data into strongly typed models.
    2. Takes the invoice totals the engine computed (key "totals"); computes none itself.
    3. Validates the invoice, then generates the mandatory 5-tag TLV QR code.
    Returns the validated ZatcaInvoice. Not yet verified against the ZATCA sandbox.
    """
    # 0. Refuse missing mandatory fields instead of inventing values
    missing = [f"invoice: {k}" for k in REQUIRED_INVOICE_KEYS if invoice_dict.get(k) in (None, "", [], {})]
    for idx, item_data in enumerate(invoice_dict.get("lines") or [], start=1):
        missing += [f"line {idx}: {k}" for k in REQUIRED_LINE_KEYS if item_data.get(k) in (None, "")]
    totals_in = invoice_dict.get("totals") or {}
    if totals_in:
        missing += [f"totals: {k}" for k in REQUIRED_TOTAL_KEYS if totals_in.get(k) in (None, "")]
    if missing:
        raise ZatcaValidationError(
            f"{len(missing)} mandatory field(s) missing", errors=[f"Missing {m}" for m in missing]
        )

    # 1. Parse Seller
    seller_data = invoice_dict.get("seller", {})
    seller_addr_data = seller_data.get("address", {})
    seller_addr = ZatcaAddress(
        street=seller_addr_data.get("street", ""),
        building_no=str(seller_addr_data.get("building_no", "")),
        postal_code=str(seller_addr_data.get("postal_code", "")),
        city=seller_addr_data.get("city", ""),
        district=seller_addr_data.get("district", ""),
        country_code=seller_addr_data.get("country_code", "SA"),
    )
    seller = ZatcaParty(
        name=seller_data.get("name", ""),
        vat_number=str(seller_data.get("vat_number", "")),
        address=seller_addr,
        name_ar=seller_data.get("name_ar"),
        cr_number=seller_data.get("cr_number"),
    )

    # 2. Parse Buyer (if present)
    buyer = None
    buyer_data = invoice_dict.get("buyer")
    if buyer_data:
        buyer_addr_data = buyer_data.get("address", {})
        buyer_addr = ZatcaAddress(
            street=buyer_addr_data.get("street", ""),
            building_no=str(buyer_addr_data.get("building_no", "")),
            postal_code=str(buyer_addr_data.get("postal_code", "")),
            city=buyer_addr_data.get("city", ""),
            district=buyer_addr_data.get("district", ""),
            country_code=buyer_addr_data.get("country_code", "SA"),
        )
        buyer = ZatcaParty(
            name=buyer_data.get("name", ""),
            vat_number=str(buyer_data.get("vat_number")) if buyer_data.get("vat_number") else None,
            address=buyer_addr,
            name_ar=buyer_data.get("name_ar"),
            cr_number=buyer_data.get("cr_number"),
            buyer_id_type=buyer_data.get("buyer_id_type"),
            buyer_id_value=buyer_data.get("buyer_id_value"),
        )

    # 3. Parse Line Items
    lines = []
    for item_data in invoice_dict.get("lines", []):
        line = ZatcaLineItem(
            item_code=item_data.get("item_code", ""),
            description=item_data.get("description", ""),
            quantity=to_decimal(item_data["quantity"]),
            unit_price=to_decimal(item_data["unit_price"]),
            vat_rate=to_decimal(item_data["vat_rate"]),
            discount=to_decimal(item_data.get("discount", "0")),  # absent means no discount
            vat_category=item_data["vat_category"],
            exemption_reason_code=item_data.get("exemption_reason_code"),
            exemption_reason_text=item_data.get("exemption_reason_text"),
        )
        lines.append(line)

    totals = ZatcaTaxTotal(
        total_taxable_amount=to_decimal(totals_in["total_taxable_amount"]),
        total_vat_amount=to_decimal(totals_in["total_vat_amount"]),
        grand_total=to_decimal(totals_in["grand_total"]),
    )

    invoice = ZatcaInvoice(
        invoice_id=invoice_dict["invoice_id"],
        issue_date=invoice_dict["issue_date"],
        issue_time=invoice_dict["issue_time"],
        timezone=invoice_dict["timezone"],
        invoice_type=invoice_dict["invoice_type"].lower(),
        transaction_type=invoice_dict["transaction_type"].lower(),
        seller=seller,
        totals=totals,
        buyer=buyer,
        lines=lines,
        currency=invoice_dict["currency"],
        preceding_invoice_reference=invoice_dict.get("preceding_invoice_reference"),
        amendment_reason=invoice_dict.get("amendment_reason"),
    )

    # 4. Validate, then generate the Phase 1 TLV QR code (raises on any validation error)
    generate_phase1_qr(invoice)
    return invoice
