# ERPGulf ZATCA App Evaluation (CMP-002)

Status: draft
Owner: partner

Task: `CMP-002` (G1 plan row depending on `ERP-001`, currently `doing` in [../PLAN.md](../PLAN.md)).
Gate note: `CMP-002` is a `G1` row while the current gate is `G0` ([../GATES.md](../GATES.md)). This document is early evidence, not a gate deliverable; runtime and ZATCA sandbox conformance remain `UNVERIFIED` until `ERP-001` provides a live bench.

- Upstream repository: [github.com/ERPGulf/zatca_erpgulf](https://github.com/ERPGulf/zatca_erpgulf) (accessed 2026-11-14)
- Evaluated release / tag: `v3.0.1` (`__version__ = "3.0.1"` in [zatca_erpgulf/__init__.py](https://github.com/ERPGulf/zatca_erpgulf/blob/main/zatca_erpgulf/__init__.py), tag commit `d906ba7` authored `2026-02-22` at [commit d906ba7](https://github.com/ERPGulf/zatca_erpgulf/commit/d906ba70ad95ae985c9fe3cc5debbb7782f9a82a), GitHub release published `2026-07-22` at [releases/tag/v3.0.1](https://github.com/ERPGulf/zatca_erpgulf/releases/tag/v3.0.1), accessed 2026-11-14)
- Upstream `main` branch head inspected: `c3fabcb` (`2026-11-13`, [commits/main](https://github.com/ERPGulf/zatca_erpgulf/commits/main), accessed 2026-11-14)

---

## 1. Executive Verdict

| Evaluation Dimension | Verdict | Summary |
|---|---|---|
| **Licence & IP Safety** | **PASS (Provisional — direct deps only)** | Permissive MIT licence (`Copyright (c) 2024 ERPGulf`, [LICENSE](https://github.com/ERPGulf/zatca_erpgulf/blob/main/LICENSE), accessed 2026-11-14). Checked direct and runtime dependencies show no AGPL licence; the full transitive dependency tree was not audited (`UNVERIFIED`). |
| **Phase 2 Technical Coverage** | **QUALIFIED PASS (Code inspection only; runtime UNVERIFIED)** | Source inspection shows pure Python ECDSA `secp256k1` via `cryptography`, XML canonicalization (`c14n` via `lxml.etree`), UBL 2.1 XML generation, TLV QR encoding, CSR configuration, and clearance/reporting API calls without an external Java SDK or ZATCA CLI binary. Actual ZATCA validator and sandbox pass is `UNVERIFIED`. |
| **Code Quality & Maintenance** | **ACTION REQUIRED** | Active upstream commits in 2026, but zero automated test coverage (`test_*.py` files contain `pass` stubs) and CI workflow targets `raven` instead of this app. Heavy custom fields on core ERPNext DocTypes, non-transactional `custom_pih` writes, and Desk UI coupling (`show_gif`) violate engine invisibility ([ADR-0016](../decisions/ADR-0016-engine-invisibility.md)). |
| **Architecture Recommendation (`PROPOSED`)** | **PROPOSED: ADOPT WITH WRAPPER / VENDOR CORE LOGIC** | `PROPOSED` choice requiring an ADR before implementation: adopt the pure Python crypto and UBL XML logic via a wrapper or vendor into `components/compliance/zatca` or `apps/engine/zatca_engine`; do **not** run the unmanaged upstream app in production. Any vendoring requires its own dedicated PR with a `PROVENANCE.md` (and [../../NOTICE.md](../../NOTICE.md) update). |

---

## 2. Licence and Legal Analysis

### 2.1 Upstream Licence Verification
- **Licence:** MIT License ([LICENSE](https://github.com/ERPGulf/zatca_erpgulf/blob/main/LICENSE), accessed 2026-11-14); [hooks.py](https://github.com/ERPGulf/zatca_erpgulf/blob/main/zatca_erpgulf/hooks.py) (accessed 2026-11-14) declares `app_license = "mit"`.
- **Copyright:** `Copyright (c) 2024 ERPGulf` in root `LICENSE`. Note that root `license.txt` ([license.txt](https://github.com/ERPGulf/zatca_erpgulf/blob/main/license.txt), accessed 2026-11-14) retains an unedited MIT template placeholder (`Copyright (c) [year] [fullname]`).
- **Declared direct dependencies** ([pyproject.toml](https://github.com/ERPGulf/zatca_erpgulf/blob/main/pyproject.toml) and [requirements.txt](https://github.com/ERPGulf/zatca_erpgulf/blob/main/requirements.txt), accessed 2026-11-14):
  - `asn1>=2.7.0,<3.0.0`: **MIT** ([PyPI asn1](https://pypi.org/project/asn1/), [PyPI JSON](https://pypi.org/pypi/asn1/json), accessed 2026-11-14).
  - `pikepdf>=8.0.0,<10.0.0`: **MPL-2.0** ([PyPI pikepdf](https://pypi.org/project/pikepdf/), [PyPI JSON](https://pypi.org/pypi/pikepdf/json), [pikepdf LICENSE.txt](https://github.com/pikepdf/pikepdf/blob/main/LICENSE.txt), accessed 2026-11-14; checked PyPI metadata for `8.9.0`, `9.11.0`, and `10.18.1` — all `MPL-2.0`). MPL-2.0 is weak file-level copyleft on pikepdf's own source if modified and distributed (SaaS use does not distribute). Binary wheels also document bundled third-party components (`qpdf` Apache-2.0; `musllinux` wheels include GCC runtime libraries under `GPL-3.0-or-later` with `GCC-exception-3.1`) in [pikepdf third-party-licenses/README.md](https://github.com/pikepdf/pikepdf/blob/main/third-party-licenses/README.md) (accessed 2026-11-14).
- **Direct Python imports supplied by the Frappe runtime or transitive environment** (imported in [sign_invoice_first.py](https://github.com/ERPGulf/zatca_erpgulf/blob/main/zatca_erpgulf/zatca_erpgulf/sign_invoice_first.py), [sign_invoice.py](https://github.com/ERPGulf/zatca_erpgulf/blob/main/zatca_erpgulf/zatca_erpgulf/sign_invoice.py), and [create_qr.py](https://github.com/ERPGulf/zatca_erpgulf/blob/main/zatca_erpgulf/zatca_erpgulf/create_qr.py); Frappe v15 dependencies in [frappe pyproject.toml](https://github.com/frappe/frappe/blob/version-15/pyproject.toml), accessed 2026-11-14):
  - `cryptography`: **Apache-2.0 OR BSD-3-Clause** ([PyPI cryptography](https://pypi.org/project/cryptography/), [PyPI JSON](https://pypi.org/pypi/cryptography/json), accessed 2026-11-14).
  - `lxml`: **BSD-3-Clause** ([PyPI lxml](https://pypi.org/project/lxml/), [PyPI JSON](https://pypi.org/pypi/lxml/json), accessed 2026-11-14).
  - `requests`: **Apache-2.0** ([PyPI requests](https://pypi.org/project/requests/), [PyPI JSON](https://pypi.org/pypi/requests/json), accessed 2026-11-14).
  - `pyqrcode` (`PyQRCode`): **BSD** (`License :: OSI Approved :: BSD License` on PyPI; [PyPI PyQRCode](https://pypi.org/project/PyQRCode/), [PyPI JSON](https://pypi.org/pypi/pyqrcode/json), accessed 2026-11-14).
- **Transitive dependency tree:** Not audited (`UNVERIFIED`). No AGPL licence was found in the upstream app or the checked direct/runtime dependencies above.

### 2.2 Comparison with Alternatives
- **Lavaloon KSA Compliance (`lavaloon-eg/ksa_compliance`):** Licensed under **GNU AGPL-3.0** ([LICENSE](https://github.com/lavaloon-eg/ksa_compliance/blob/master/LICENSE), [GitHub API](https://api.github.com/repos/lavaloon-eg/ksa_compliance), accessed 2026-11-14). Under Rule 34 ([../RULES.md](../RULES.md)) and [ADR-0002](../decisions/ADR-0002-seed-engine-frappe-erpnext.md), AGPL components are forbidden.
- **Odoo EDI (`addons/l10n_sa_edi`):** Licensed under **LGPL-3** ([__manifest__.py](https://github.com/odoo/odoo/blob/18.0/addons/l10n_sa_edi/__manifest__.py), [Odoo LICENSE](https://github.com/odoo/odoo/blob/18.0/LICENSE), accessed 2026-11-14), and coupled to Odoo's model/ORM architecture rather than Frappe/ERPNext.
- **Verdict:** Among the three options compared here, ERPGulf is the only MIT-licensed Frappe/ERPNext option. A broader market survey of other Frappe or standalone Python ZATCA libraries was not performed (`UNVERIFIED`).

---

## 3. ZATCA Phase 2 Coverage & Feature Audit

All findings in Section 3 come from static inspection of upstream source files on 2026-11-14. Runtime execution on a bench and validation against the ZATCA SDK validator or sandbox remain `UNVERIFIED` (`CMP-003`, `CMP-004`).

### 3.1 Implemented Capabilities (Static Inspection)
1. **CSR Generation ([csr_configuration.py](https://github.com/ERPGulf/zatca_erpgulf/blob/main/zatca_erpgulf/zatca_erpgulf/csr_configuration.py), [sign_invoice_first.py](https://github.com/ERPGulf/zatca_erpgulf/blob/main/zatca_erpgulf/zatca_erpgulf/sign_invoice_first.py), accessed 2026-11-14):**
   - Pure Python generation of `secp256k1` ECDSA keys via `cryptography` (`ec.generate_private_key(ec.SECP256K1())`).
   - Builds CSR configuration and encodes ZATCA ASN.1 OID extensions using `asn1`.
2. **Onboarding API Calls ([sign_invoice_first.py](https://github.com/ERPGulf/zatca_erpgulf/blob/main/zatca_erpgulf/zatca_erpgulf/sign_invoice_first.py), [sign_invoice.py](https://github.com/ERPGulf/zatca_erpgulf/blob/main/zatca_erpgulf/zatca_erpgulf/sign_invoice.py), accessed 2026-11-14):**
   - Calls ZATCA `/compliance` (`create_csid`), `/compliance/invoices` (`compliance_api_call`), and `/production/csids` (`production_csid`) via `requests`.
   - Routes Sandbox, Simulation, and Production URLs via `get_api_url`.
3. **UBL 2.1 XML Construction ([createxml.py](https://github.com/ERPGulf/zatca_erpgulf/blob/main/zatca_erpgulf/zatca_erpgulf/createxml.py), [create_xml_final_part.py](https://github.com/ERPGulf/zatca_erpgulf/blob/main/zatca_erpgulf/zatca_erpgulf/create_xml_final_part.py), [xml_tax_data.py](https://github.com/ERPGulf/zatca_erpgulf/blob/main/zatca_erpgulf/zatca_erpgulf/xml_tax_data.py), accessed 2026-11-14):**
   - Constructs standard (`0100000`) and simplified (`0200000`) invoice XML with type codes `388` (invoice), `381` (credit note), and `383` (debit note), plus `company_data` / `customer_data`. Full ZATCA XSD/Schematron compliance is `UNVERIFIED`.
4. **Cryptographic Signing & Enveloping ([sign_invoice_first.py](https://github.com/ERPGulf/zatca_erpgulf/blob/main/zatca_erpgulf/zatca_erpgulf/sign_invoice_first.py), accessed 2026-11-14):**
   - XML canonicalization (`canonicalize_xml` using `lxml.etree`), SHA-256 hashing (`getinvoicehash`), ECDSA signing (`digital_signature`), and XAdES/UBL signature enveloping (`populate_the_ubl_extensions_output`).
5. **QR Code Generation ([create_qr.py](https://github.com/ERPGulf/zatca_erpgulf/blob/main/zatca_erpgulf/zatca_erpgulf/create_qr.py), [sign_invoice_first.py](https://github.com/ERPGulf/zatca_erpgulf/blob/main/zatca_erpgulf/zatca_erpgulf/sign_invoice_first.py), accessed 2026-11-14):**
   - `create_qr.py` encodes Phase 1 5-tag TLV QR images using `pyqrcode`.
   - `sign_invoice_first.py` (`generate_tlv_xml`, `tag8_publickey`, `tag9_signature_ecdsa`) adds Phase 2 TLV tags 6–9.
6. **Clearance, Reporting, & Background Queue ([sign_invoice.py](https://github.com/ERPGulf/zatca_erpgulf/blob/main/zatca_erpgulf/zatca_erpgulf/sign_invoice.py), [zatca_background_sched.py](https://github.com/ERPGulf/zatca_erpgulf/blob/main/zatca_erpgulf/zatca_erpgulf/zatca_background_sched.py), [scheduler_event.py](https://github.com/ERPGulf/zatca_erpgulf/blob/main/zatca_erpgulf/zatca_erpgulf/scheduler_event.py), accessed 2026-11-14):**
   - Clearance (`clearance_api` -> `invoices/clearance/single`), reporting (`reporting_api` -> `invoices/reporting/single`), and cron scheduling via `hooks.py`.
7. **Credit & Debit Notes ([createxml.py](https://github.com/ERPGulf/zatca_erpgulf/blob/main/zatca_erpgulf/zatca_erpgulf/createxml.py), accessed 2026-11-14):**
   - Populates `cac:BillingReference` / `cac:InvoiceDocumentReference` (`billing_reference_for_credit_and_debit_note`).
8. **Hybrid PDF/A-3 Generation ([pdf_a3.py](https://github.com/ERPGulf/zatca_erpgulf/blob/main/zatca_erpgulf/zatca_erpgulf/pdf_a3.py), accessed 2026-11-14):**
   - Embeds XML in PDF via `pikepdf`. PDF/A-3 conformance with ZATCA/veraPDF is `UNVERIFIED`.

### 3.2 Gaps and Deficiencies
1. **Concurrency and Hash Chaining (PIH/ICV) Vulnerability:**
   - `sign_invoice.py` (accessed 2026-11-14) updates `custom_pih` directly on settings/Company docs (`company_doc.custom_pih = encoded_hash`, `zatca_settings.custom_pih = encoded_hash`) without row-level database locking.
   - *Risk:* Concurrent invoice submissions can read the same PIH and break the hash chain.
   - *PROPOSED Fix:* Introduce an isolated, transactional database sequence/store with row-level locks per tenant/company.
2. **Advance Payments / Prepayments:**
   - Upstream modules [createxml_advance.py](https://github.com/ERPGulf/zatca_erpgulf/blob/main/zatca_erpgulf/zatca_erpgulf/createxml_advance.py) and [advance_payment.py](https://github.com/ERPGulf/zatca_erpgulf/blob/main/zatca_erpgulf/zatca_erpgulf/advance_payment.py) have open bugfixes in [PR #266](https://github.com/ERPGulf/zatca_erpgulf/pull/266) (accessed 2026-11-14) for `Decimal - float` TypeError and `BR-CO-04` tax-category corruption on advance invoices.
3. **Export and Nominal Invoices:**
   - Open community [PR #265](https://github.com/ERPGulf/zatca_erpgulf/pull/265) (accessed 2026-11-14) flags rounding mismatches, non-Saudi customer country-code bugs without the export flag, tax exemption category checks, and multi-currency discount bugs.
4. **Error Handling & Classification:**
   - `sign_invoice.py` writes raw status/errors into `custom_zatca_full_response`. The platform requires structured domain events and localized Arabic/English explanations in the brand voice ([ADR-0004](../decisions/ADR-0004-one-chat-role-based-views.md)).

---

## 4. Maintenance Health & Code Quality

### 4.1 Upstream Activity & Health
- **Activity:** Active on `main` in 2026; `v3.0.1` published `2026-07-22` ([releases/tag/v3.0.1](https://github.com/ERPGulf/zatca_erpgulf/releases/tag/v3.0.1), accessed 2026-11-14), latest commit on `main` `c3fabcb` on `2026-11-13` ([commits/main](https://github.com/ERPGulf/zatca_erpgulf/commits/main), accessed 2026-11-14).
- **Community metrics:** `65` stars and `95` forks on GitHub ([ERPGulf/zatca_erpgulf](https://github.com/ERPGulf/zatca_erpgulf), [GitHub API](https://api.github.com/repos/ERPGulf/zatca_erpgulf), accessed 2026-11-14). Real-world production adoption breadth is `UNVERIFIED`.
- **Issues and PRs:** `43` issues ([issues](https://github.com/ERPGulf/zatca_erpgulf/issues), accessed 2026-11-14) and `226` pull requests ([pulls](https://github.com/ERPGulf/zatca_erpgulf/pulls), accessed 2026-11-14), totaling `269` (`34` open combined as of 2026-11-14), including open PRs `#265` and `#266`.

### 4.2 Code Quality & Architectural Violations
1. **Zero Automated Test Coverage:**
   - All four `test_*.py` files in the repository ([test_zatca_erpgulf_setting.py](https://github.com/ERPGulf/zatca_erpgulf/blob/main/zatca_erpgulf/zatca_erpgulf/doctype/zatca_erpgulf_setting/test_zatca_erpgulf_setting.py), [test_zatca_erpgulf_event_log.py](https://github.com/ERPGulf/zatca_erpgulf/blob/main/zatca_erpgulf/zatca_erpgulf/doctype/zatca_erpgulf_event_log/test_zatca_erpgulf_event_log.py), [test_zatca_erpgulf_success_log.py](https://github.com/ERPGulf/zatca_erpgulf/blob/main/zatca_erpgulf/zatca_erpgulf/doctype/zatca_erpgulf_success_log/test_zatca_erpgulf_success_log.py), and [test_zatca_multiple_setting.py](https://github.com/ERPGulf/zatca_erpgulf/blob/main/zatca_erpgulf/zatca_erpgulf/doctype/zatca_multiple_setting/test_zatca_multiple_setting.py), accessed 2026-11-14) contain only `pass` stubs.
   - [.github/workflows/frappe-ci.yml](https://github.com/ERPGulf/zatca_erpgulf/blob/main/.github/workflows/frappe-ci.yml) (accessed 2026-11-14) still references `raven` rather than running tests for `zatca_erpgulf`.
2. **Severe UI & Desk Coupling:**
   - Calls `frappe.publish_realtime("show_gif", ...)` in `sign_invoice.py` and `sign_invoice_first.py`.
   - Registers Desk JS/CSS assets, `ERPGulf.png` app icon, custom pages, workspace JSON, and fixtures in [hooks.py](https://github.com/ERPGulf/zatca_erpgulf/blob/main/zatca_erpgulf/hooks.py) (accessed 2026-11-14).
   - **Violation of Engine Invisibility ([ADR-0016](../decisions/ADR-0016-engine-invisibility.md)):** The engine must remain headless and invisible.
3. **DocType Pollution:**
   - [custom_field.json](https://github.com/ERPGulf/zatca_erpgulf/blob/main/zatca_erpgulf/fixtures/custom_field.json) (accessed 2026-11-14) and runtime `create_custom_fields` calls inject `custom_*` / `custom_zatca_*` fields onto core ERPNext DocTypes (`Company`, `Customer`, `Address`, `Sales Invoice`).

---

## 5. Proposed Implementation Roadmap for the Platform

Decision record: [ADR-0042](../decisions/ADR-0042-zatca-phase-2-vendor-core-rebuild-state.md) (CMP-033, Proposed) chooses a hybrid: vendor the pure core, rebuild the chain, outbox and hooks.

Everything in this section is `PROPOSED`. Choosing between wrapping the upstream app and vendoring/extracting modules into `components/compliance/zatca` or `apps/engine/zatca_engine` is an architectural decision that **requires an ADR** before implementation. Any vendoring or import of third-party code **requires its own dedicated PR with a `PROVENANCE.md`** (recording source URL, pinned commit, kept/removed/changed files, plus updating [../../NOTICE.md](../../NOTICE.md) per Rule 17 in [../RULES.md](../RULES.md)).

To satisfy **CMP-003** (Phase 1 QR & fields) and **CMP-004** (Phase 2 sandbox clearance), the `PROPOSED` plan is:

1. **ADR & Dedicated Import/Wrapper PR (`PROPOSED`):**
   - Write an ADR deciding whether to wrap a pinned upstream release or extract pure deterministic modules (`sign_invoice_first.py`, `create_qr.py`, `createxml.py`, `xml_tax_data.py`) into the platform codebase.
   - If vendoring, open a dedicated PR with `PROVENANCE.md` and `NOTICE.md` updates, and audit the full transitive dependency tree.
   - Strip all Desk UI, GIFs, real-time notifications, icons, and workspace definitions per [ADR-0016](../decisions/ADR-0016-engine-invisibility.md).
2. **Transactional Hash Chaining (`PROPOSED`):**
   - Implement an atomic hash sequence store with database row locks (`SELECT ... FOR UPDATE`) per tenant/company for strictly sequential PIH/ICV progression.
3. **Structured Event Adapter (`PROPOSED`):**
   - Wrap ZATCA submission in an idempotent engine adapter emitting standard platform events (`invoice.clearance_requested`, `invoice.cleared`, `invoice.clearance_failed`) to the event stream (`BPL-011`).
4. **Automated Sandbox Conformance Suite (`CMP-004`, `PROPOSED`):**
   - Build a live integration test suite executing full lifecycle runs against the official ZATCA sandbox (onboarding CSR -> Compliance CSID -> Production CSID, standard B2B clearance, simplified B2C reporting, debit/credit notes, rejection/recovery) as proposed mitigation for `R-018`.

---

## 6. Document References
- [e-invoicing.md](e-invoicing.md)
- [country-matrix.md](country-matrix.md)
- [../legal/licence-register.md](../legal/licence-register.md)
- [../decisions/ADR-0002-seed-engine-frappe-erpnext.md](../decisions/ADR-0002-seed-engine-frappe-erpnext.md)
- [../decisions/ADR-0016-engine-invisibility.md](../decisions/ADR-0016-engine-invisibility.md)
