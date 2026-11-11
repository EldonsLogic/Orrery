# ERPGulf ZATCA App Evaluation (CMP-002)

Status: completed
Date: 2026-11-07
Author: partner
Task: CMP-002
Upstream repository: [https://github.com/ERPGulf/zatca_erpgulf](https://github.com/ERPGulf/zatca_erpgulf)
Evaluated version / tag: `v3.0.1` (commit `7d686f7`, released 2026-07-22, repository active through 2026-11-03)

---

## 1. Executive Verdict

| Evaluation Dimension | Verdict | Summary |
|---|---|---|
| **Licence & IP Safety** | **PASS (Approved)** | Permissive MIT licence (Copyright (c) 2024 ERPGulf). Zero AGPL contamination. Can be embedded, modified, and redistributed within our SaaS runtime. |
| **Phase 2 Technical Coverage** | **QUALIFIED PASS** | Implements the core cryptography (pure Python ECDSA secp256k1 via `cryptography`), canonicalization (c14n), UBL 2.1 XML generation, TLV QR code encoding, CSR generation, and clearance/reporting API endpoints. No external Java SDK or ZATCA CLI binary required. |
| **Code Quality & Maintenance** | **ACTION REQUIRED** | Community-maintained with frequent commits but zero automated test coverage (test classes contain only `pass`). Heavy monkey-patching of standard ERPNext DocTypes. UI coupling (`frappe.publish_realtime("show_gif")`) violates engine invisibility (ADR-0016). |
| **Architecture Recommendation** | **ADOPT WITH WRAPPER** | Adopt the pure Python cryptographic and XML generation logic; do **not** run unmanaged upstream app in production. Vendor/fork into `components/compliance/zatca` or `apps/engine/zatca_engine`, strip all Desk UI/branding, make PIH hash chaining transactional, and build automated sandbox conformance tests (CMP-004). |

---

## 2. Licence and Legal Analysis

### 2.1 Upstream Licence Verification
- **Licence:** MIT License.
- **Copyright:** `Copyright (c) 2024 ERPGulf`.
- **Licence text location:** Root `LICENSE` and `license.txt` in upstream repo.
- **Dependency chain:**
  - `cryptography` (Apache-2.0 / BSD-3-Clause)
  - `lxml` (BSD-3-Clause)
  - `asn1>=2.7.0,<3.0.0` (MIT)
  - `pikepdf>=8.0.0,<10.0.0` (Mozilla Public License 2.0 / LGPL-3.0+)
  - `requests` (Apache-2.0)
  - `pyqrcode` (BSD-3-Clause)

### 2.2 Comparison with Alternatives
- **Lavaloon KSA Compliance (`lavaloon-eg/ksa_compliance`):** Licensed under **GNU AGPL v3.0**. Under Rule 34 and ADR-0002, AGPL components are strictly forbidden because network interactions would trigger copyleft disclosure requirements for proprietary platform components.
- **Odoo EDI (`addons/l10n_sa_edi`):** LGPL-3.0, but tied to Odoo model architecture and not reusable in Frappe/ERPNext without substantial rewriting.
- **Verdict:** ERPGulf's MIT licence is the only viable, commercially permissive open-source base for Frappe/ERPNext e-invoicing.

---

## 3. ZATCA Phase 2 Coverage & Feature Audit

### 3.1 Implemented Capabilities
1. **CSR Generation (`csr_configuration.py`, `sign_invoice_first.py`):**
   - Pure Python generation of secp256k1 ECDSA private keys.
   - Generates Certificate Signing Request (CSR) with required ZATCA ASN.1 OIDs (Organisation Identifier, Serial Number, Invoice Type, Location Address, Industry Category).
2. **Onboarding API Calls:**
   - Obtains Compliance CSID via ZATCA `/compliance` endpoint using OTP.
   - Obtains Production CSID via `/production/csids`.
   - Supports Sandbox, Simulation, and Production endpoint routing (`get_api_url`).
3. **UBL 2.1 XML Construction (`createxml.py`, `create_xml_final_part.py`, `xml_tax_data.py`):**
   - Constructs standard tax invoice and simplified tax invoice XML documents compliant with ZATCA Phase 2 schema.
   - Populates mandatory party details (Seller, Buyer with VAT / National ID / CRN / MOMRAH / MLSD identifiers).
   - Generates invoice type codes (`0100000` for standard, `0200000` for simplified, plus debit/credit flags).
4. **Cryptographic Signing & Enveloping (`sign_invoice_first.py`):**
   - XML canonicalization (`c14n` via `lxml.etree`).
   - SHA-256 invoice hashing (`getinvoicehash`).
   - Digital signature generation using the tenant private key.
   - XAdES signature enveloping (`ext:UBLExtensions`, `sig:UBLDocumentSignatures`).
5. **Phase 2 QR Code Generation (`create_qr.py`):**
   - TLV (Tag-Length-Value) encoding for 9 ZATCA tags: Seller Name (1), VAT Number (2), Timestamp (3), Invoice Total (4), VAT Total (5), Invoice Hash (6), Digital Signature (7), Public Key (8), and Certificate Signature (9).
6. **Clearance & Reporting Integration (`sign_invoice.py`):**
   - Standard Invoices (B2B): Synchronous clearance call to `invoices/clearance/single`. Stores clearance status and signed XML.
   - Simplified Invoices (B2C): Asynchronous reporting call to `invoices/reporting/single` (within 24-hour window) or immediate submission.
   - Background worker: Scheduled queue in `zatca_background_sched.py`.
7. **Credit & Debit Notes:**
   - Supported via `cac:BillingReference` and `cac:InvoiceDocumentReference` linking back to the original invoice UUID and hash.
8. **Hybrid PDF/A-3 Generation (`pdf_a3.py`):**
   - Embeds the cleared/reported signed UBL XML inside a PDF/A-3 container using `pikepdf`.

### 3.2 Gaps and Deficiencies
1. **Concurrency and Hash Chaining (PIH/ICV) Vulnerability:**
   - ERPGulf updates the Previous Invoice Hash (`custom_pih`) directly on the `Company` DocType:
     ```python
     company_doc.custom_pih = encoded_hash
     company_doc.save(ignore_permissions=True)
     ```
   - *Risk:* In a multi-user or high-volume system, concurrent invoice submissions create race conditions where two invoices read the same PIH, breaking the cryptographic hash chain and causing ZATCA sandbox/production rejections.
   - *Fix:* Must introduce an isolated, transactional database queue with row-level locks or an atomic counter sequence.
2. **Advance Payments / Prepayments:**
   - Upstream code has fragmented logic (`createxml_advance.py`, PR #266). Edge cases exist around multi-currency advances and tax reconciliation.
3. **Export and Nominal Invoices:**
   - Buyer identity validation and VAT exemption codes for export / GCC cross-border invoices have edge-case issues reported in upstream PR #265.
4. **Error Handling & Classification:**
   - Raw HTTP responses and validation errors are dumped as unparsed text into `custom_zatca_full_response`.
   - The platform requires structured domain events emitting machine-readable error codes and localized Arabic/English explanations in the brand voice (ADR-0004).

---

## 4. Maintenance Health & Code Quality

### 4.1 Upstream Activity & Health
- **Activity:** Active. Multiple commits in 2026; release `v3.0.1` tagged July 2026; last pushed November 2026.
- **Community:** Used widely in Saudi Frappe community, with frequent contributions from local practitioners.
- **Issues/PRs:** ~270 total issues and PRs. Notable active discussions on rounding issues, address formatting, and advance invoices.

### 4.2 Code Quality & Architectural Violations
1. **Zero Test Coverage:**
   - Upstream `test_*.py` files are empty stubs with `pass` statements. There is no automated test suite validating invoices against the ZATCA validator or sandbox.
2. **Severe UI & Desk Coupling:**
   - Calls `frappe.publish_realtime("show_gif", ...)` to display animated loading GIFs in Desk.
   - Injects custom pages, workspace shortcuts, and desktop icons.
   - **Violation of Engine Invisibility (ADR-0016):** The engine must remain headless. Customers must never observe third-party app branding, Desk notifications, or unskinned UI elements.
3. **DocType Pollution:**
   - Adds dozens of fields prefixed with `custom_zatca_` or `custom_` directly into ERPNext core DocTypes (`Company`, `Customer`, `Address`, `Sales Invoice`).

---

## 5. Implementation Roadmap for Orrery

To satisfy **CMP-003** (Phase 1 QR & fields) and **CMP-004** (Phase 2 sandbox clearance), we must execute the following architectural plan:

1. **Vendor & Decouple Core Logic:**
   - Extract the pure deterministic modules (`sign_invoice_first.py`, `create_qr.py`, `createxml.py`, `xml_tax_data.py`) into our platform engine codebase.
   - Strip all Desk UI, GIFs, real-time desk notifications, and workspace definitions.
2. **Transactional Hash Chaining:**
   - Implement an atomic hash sequence store with database row locks (`SELECT ... FOR UPDATE`) per tenant/company to ensure strictly sequential PIH/ICV progression.
3. **Structured Event Adapter:**
   - Wrap ZATCA submission in an idempotent engine adapter that emits standard platform events (`invoice.clearance_requested`, `invoice.cleared`, `invoice.clearance_failed`) to the event stream (BPL-011).
4. **Automated Sandbox Conformance Suite (CMP-004):**
   - Create a dedicated integration test suite executing full lifecycle runs against the official ZATCA sandbox:
     - Onboarding (CSR -> Compliance CSID -> Production CSID)
     - Standard B2B Invoice Clearance
     - Simplified B2C Invoice Reporting
     - Debit Note & Credit Note with reference chaining
     - Rejection and failure error recovery
   - Run in CI to prevent regression (R-018 mitigation).

---

## 6. Document References
- [e-invoicing.md](e-invoicing.md)
- [country-matrix.md](country-matrix.md)
- [../legal/licence-register.md](../legal/licence-register.md)
- [../decisions/ADR-0002-seed-engine-frappe-erpnext.md](../decisions/ADR-0002-seed-engine-frappe-erpnext.md)
- [../decisions/ADR-0016-engine-invisibility.md](../decisions/ADR-0016-engine-invisibility.md)
