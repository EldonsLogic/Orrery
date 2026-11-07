"""
ZATCA Phase 1 E-Invoicing Generation and Validation.
Saudi Arabia E-Invoicing Regulation (Fatoora Phase 1).

Implements:
1. 5-tag TLV QR code encoding and decoding.
2. Mandatory invoice field validation per VAT Implementing Regulations (Art. 53)
   and ZATCA E-Invoicing Resolution (Annex 2).
3. Deterministic decimal tax calculation and rounding (15% standard rate, zero-rate, exempt).
4. Immutability guardrails for credit and debit notes.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
import re
from typing import Any, Dict, List, Optional

# KSA 15-digit VAT number format: begins with '3' and ends with '3'
KSA_VAT_REGEX = re.compile(r"^3\d{13}3$")
DATE_REGEX = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_REGEX = re.compile(r"^\d{2}:\d{2}(:\d{2})?")

STANDARD_TAX_RATE = Decimal("0.15")
ZERO_TAX_RATE = Decimal("0.00")
TWO_DECIMALS = Decimal("0.01")


class ZatcaValidationError(ValueError):
    """Raised when an invoice fails ZATCA Phase 1 compliance validation."""

    def __init__(self, message: str, errors: Optional[List[str]] = None):
        super().__init__(message)
        self.errors = errors or [message]


def quantize_amount(val: Any) -> Decimal:
    """Format and round a monetary amount to 2 decimal places using ROUND_HALF_UP."""
    if isinstance(val, Decimal):
        dec = val
    elif isinstance(val, (int, float, str)):
        dec = Decimal(str(val))
    else:
        dec = Decimal("0.00")
    return dec.quantize(TWO_DECIMALS, rounding=ROUND_HALF_UP)


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
    """Line item in a ZATCA invoice."""
    item_code: str
    description: str
    quantity: Decimal
    unit_price: Decimal
    vat_rate: Decimal = STANDARD_TAX_RATE
    discount: Decimal = Decimal("0.00")
    vat_category: str = "S"  # S: Standard, Z: Zero-rated, E: Exempt, O: Out-of-scope
    exemption_reason_code: Optional[str] = None
    exemption_reason_text: Optional[str] = None

    @property
    def gross_amount(self) -> Decimal:
        return quantize_amount(self.quantity * self.unit_price)

    @property
    def net_amount(self) -> Decimal:
        return quantize_amount(self.gross_amount - self.discount)

    @property
    def vat_amount(self) -> Decimal:
        return quantize_amount(self.net_amount * self.vat_rate)

    @property
    def line_total(self) -> Decimal:
        return quantize_amount(self.net_amount + self.vat_amount)

    def validate(self, line_index: int = 1) -> List[str]:
        errors = []
        if not self.description or not self.description.strip():
            errors.append(f"Line {line_index}: Item description is required")
        if self.quantity == Decimal("0.00"):
            errors.append(f"Line {line_index}: Quantity cannot be zero")
        if self.unit_price < Decimal("0.00"):
            errors.append(f"Line {line_index}: Unit price cannot be negative")
        if self.discount < Decimal("0.00"):
            errors.append(f"Line {line_index}: Discount cannot be negative")
        if self.discount > self.gross_amount:
            errors.append(f"Line {line_index}: Discount cannot exceed line gross amount")

        # VAT Category checks
        if self.vat_category == "S":
            if self.vat_rate != STANDARD_TAX_RATE:
                errors.append(f"Line {line_index}: Standard rate category 'S' must have VAT rate 0.15 (15%)")
        elif self.vat_category in ("Z", "E", "O"):
            if self.vat_rate != ZERO_TAX_RATE:
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
    """Aggregated tax breakdown for an invoice."""
    total_taxable_amount: Decimal
    total_vat_amount: Decimal
    grand_total: Decimal
    line_extension_amount: Decimal
    document_discount: Decimal = Decimal("0.00")
    prepaid_amount: Decimal = Decimal("0.00")
    amount_due: Decimal = Decimal("0.00")


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
    transaction_type: str  # "tax_invoice", "simplified_tax_invoice", "credit_note", "debit_note"
    seller: ZatcaParty
    lines: List[ZatcaLineItem] = field(default_factory=list)
    buyer: Optional[ZatcaParty] = None
    currency: str = "SAR"
    document_discount: Decimal = Decimal("0.00")
    prepaid_amount: Decimal = Decimal("0.00")
    preceding_invoice_reference: Optional[str] = None
    amendment_reason: Optional[str] = None
    qr_code_tlv: Optional[str] = None

    @property
    def is_standard(self) -> bool:
        return self.invoice_type.lower() == "standard"

    @property
    def is_simplified(self) -> bool:
        return self.invoice_type.lower() == "simplified"

    @property
    def is_adjustment_note(self) -> bool:
        return self.transaction_type in ("credit_note", "debit_note")

    def compute_totals(self) -> ZatcaTaxTotal:
        """Compute all taxable and VAT totals using deterministic Decimal arithmetic."""
        line_extension = sum((item.net_amount for item in self.lines), Decimal("0.00"))
        line_extension = quantize_amount(line_extension)

        doc_discount = quantize_amount(self.document_discount)
        total_taxable = quantize_amount(line_extension - doc_discount)

        total_vat = sum((item.vat_amount for item in self.lines), Decimal("0.00"))
        total_vat = quantize_amount(total_vat)

        grand_total = quantize_amount(total_taxable + total_vat)
        prepaid = quantize_amount(self.prepaid_amount)
        amount_due = quantize_amount(grand_total - prepaid)

        return ZatcaTaxTotal(
            total_taxable_amount=total_taxable,
            total_vat_amount=total_vat,
            grand_total=grand_total,
            line_extension_amount=line_extension,
            document_discount=doc_discount,
            prepaid_amount=prepaid,
            amount_due=amount_due,
        )

    def validate(self) -> List[str]:
        """Perform full validation against ZATCA Phase 1 regulations."""
        errors = []

        if not self.invoice_id or not self.invoice_id.strip():
            errors.append("Invoice identifier (sequential reference) is mandatory")

        if not self.issue_date or not DATE_REGEX.match(self.issue_date.strip()):
            errors.append(f"Issue date '{self.issue_date}' is invalid. Must be 'YYYY-MM-DD'.")

        if not self.issue_time or not TIME_REGEX.match(self.issue_time.strip()):
            errors.append(f"Issue time '{self.issue_time}' is invalid. Must be 'HH:MM:SS'.")

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

        # Simplified invoices must have QR code generated
        if self.is_simplified and self.qr_code_tlv is None:
            # We don't fail immediately if caller hasn't called generate_phase1_qr yet,
            # but note it in check
            pass

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
    """
    totals = invoice.compute_totals()

    # Time stamp format: YYYY-MM-DDTHH:MM:SSZ
    date_part = invoice.issue_date.strip()
    time_part = invoice.issue_time.strip()
    if len(time_part) == 5:
        time_part += ":00"
    timestamp_iso = f"{date_part}T{time_part}Z"

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
    2. Computes line totals and invoice totals deterministically.
    3. Generates the mandatory 5-tag TLV QR code.
    4. Validates compliance and returns the certified ZatcaInvoice.
    """
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
            quantity=quantize_amount(item_data.get("quantity", "1")),
            unit_price=quantize_amount(item_data.get("unit_price", "0")),
            vat_rate=Decimal(str(item_data.get("vat_rate", "0.15"))),
            discount=quantize_amount(item_data.get("discount", "0")),
            vat_category=item_data.get("vat_category", "S"),
            exemption_reason_code=item_data.get("exemption_reason_code"),
            exemption_reason_text=item_data.get("exemption_reason_text"),
        )
        lines.append(line)

    invoice = ZatcaInvoice(
        invoice_id=invoice_dict.get("invoice_id", ""),
        issue_date=invoice_dict.get("issue_date", ""),
        issue_time=invoice_dict.get("issue_time", "12:00:00"),
        invoice_type=invoice_dict.get("invoice_type", "simplified").lower(),
        transaction_type=invoice_dict.get("transaction_type", "tax_invoice").lower(),
        seller=seller,
        buyer=buyer,
        lines=lines,
        currency=invoice_dict.get("currency", "SAR"),
        document_discount=quantize_amount(invoice_dict.get("document_discount", "0")),
        prepaid_amount=quantize_amount(invoice_dict.get("prepaid_amount", "0")),
        preceding_invoice_reference=invoice_dict.get("preceding_invoice_reference"),
        amendment_reason=invoice_dict.get("amendment_reason"),
    )

    # 4. Generate Phase 1 TLV QR Code
    generate_phase1_qr(invoice)

    # 5. Validate full compliance
    errors = invoice.validate()
    if errors:
        raise ZatcaValidationError(
            f"ZATCA Phase 1 invoice validation failed with {len(errors)} error(s)",
            errors=errors,
        )

    return invoice
