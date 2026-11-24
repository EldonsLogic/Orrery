# ADR-0037: ZATCA Phase 2: vendor the ERPGulf app's pure core, rebuild everything that touches state

Status: Proposed
Owner: partner
Approved by: pending (the partner accepts or amends; Tier 2 under ADR-0035 as an ADR, then the other founder's review)

## Context
CMP-004 (G1) needs a ZATCA Phase 2 invoice that passes the ZATCA sandbox: signing, hash chain, clearance and reporting. CMP-002 evaluated the only MIT-licensed Frappe/ERPNext option, the ERPGulf ZATCA app ([zatca-erpgulf-evaluation.md](../compliance/zatca-erpgulf-evaluation.md)). The AGPL Lavaloon app is forbidden (RULES 34, ADR-0002). The evaluation proposed "adopt with wrapper or vendor core logic" and required an ADR before any build. That is this record (CMP-033).

What the evaluation found, and what this ADR re-checked:
- **Licence.** MIT, `Copyright (c) 2024 ERPGulf` ([LICENSE](https://github.com/ERPGulf/zatca_erpgulf/blob/main/LICENSE), accessed 2026-11-18); the GitHub API reports `spdx_id: MIT` ([repos/ERPGulf/zatca_erpgulf](https://api.github.com/repos/ERPGulf/zatca_erpgulf), accessed 2026-11-18). Root `license.txt` still holds the unfilled MIT template. Direct and runtime dependencies are permissive (pikepdf MPL-2.0); the transitive tree is UNVERIFIED. Recorded in the [licence register](../legal/licence-register.md) (LEG-004).
- **Upstream state.** Tag `v3.0.1` is commit `d906ba7` ([release](https://github.com/ERPGulf/zatca_erpgulf/releases/tag/v3.0.1), accessed 2026-11-14). `main` head at this writing is `015eaf80b7d2a910c73a2eca553bbafa1410dbfa` (2026-11-16, [commits/main](https://github.com/ERPGulf/zatca_erpgulf/commits/main), accessed 2026-11-18). The function and line references below are from that commit.
- **No tests.** All four `test_*.py` files are `pass` stubs; the CI workflow targets another app (evaluation 4.2).
- **Non-transactional chain.** `sign_invoice.py` writes the previous-invoice hash straight onto the Company or settings record (`company_doc.custom_pih = encoded_hash`, lines 409-500) without a row lock, so concurrent submissions can read the same PIH and fork the chain (evaluation 3.2).
- **ICV is not a counter.** `createxml.get_icv_code` (line 18) strips the non-digits out of the invoice name and uses the rest as the ICV. It is not an allocated sequence.
- **Desk coupling.** `frappe.publish_realtime("show_gif" / "hide_gif")` in `sign_invoice_first.py` (lines 368, 380, 1365) and `sign_invoice.py`, Desk assets, workspace and custom pages in `hooks.py`, and `custom_*` fields on `Company`, `Customer`, `Address` and `Sales Invoice` (evaluation 4.2). That conflicts with ADR-0016 (engine invisible, headless).
- **Keys in records.** `create_private_keys` (line 118) writes the private key as unencrypted PEM (`NoEncryption()`) into a document field; `digital_signature` (line 558) reads it back from the Company or settings record. That conflicts with key custody in the threat model (T10, SEC-002, SEC-011).

So the stateful half of the app (chain, counter, queue, hooks, keys) is the half we cannot use. The stateless half (key and CSR generation, XML, canonicalisation, hashing, signing, QR TLV) holds real ZATCA know-how we should not rewrite blind.

## Decision
**Hybrid. Vendor the app's pure-Python core; rebuild everything that touches state.**

### 1. Vendor (MIT, with a `PROVENANCE.md`, only what is needed, pinned commit)
The candidate upstream units, all under `zatca_erpgulf/zatca_erpgulf/` at commit `015eaf8`:

| Capability | Upstream file and functions | Confirmed |
|---|---|---|
| ECDSA key and CSR generation | `sign_invoice_first.py`: `create_private_keys` (118, `ec.generate_private_key(ec.SECP256K1())`), `create_csr` (168), `encode_customoid` (28), `parse_csr_config` (37); `csr_configuration.py`: `get_csr_config` (9) | names and lines read; behaviour UNVERIFIED |
| UBL 2.1 XML builders | `createxml.py`: `xml_tags` (71), `salesinvoice_data` (204), `invoice_typecode_simplified` / `_standard` (286, 322), `doc_reference` (359), `additional_reference` (441), `company_data` (571), `customer_data` (649), `billing_reference_for_credit_and_debit_note` (45), `delivery_and_payment_means` (773); `xml_tax_data.py`: `tax_data` (119), `tax_data_with_template` (487); `create_xml_final_part.py`: `item_data` (650), `item_data_with_template` (1115), `xml_structuring` (1491) | names and lines read; XSD and Schematron conformance UNVERIFIED |
| Canonicalisation, hash and signing | `sign_invoice_first.py`: `removetags` (501, XSLT that drops `UBLExtensions`, the QR reference and `Signature`), `canonicalize_xml` (534, lxml `c14n`), `getinvoicehash` (544, SHA-256), `digital_signature` (558, `ec.ECDSA(hashes.SHA256())`), `certificate_hash` (663), `signxml_modify` (728), `generate_signed_properties_hash` (786), `populate_the_ubl_extensions_output` (827) | names and lines read; correctness against ZATCA vectors UNVERIFIED |
| TLV and QR encoding | `sign_invoice_first.py`: `get_tlv_for_value` (954), `tag8_publickey` (976), `tag9_signature_ecdsa` (992), `generate_tlv_xml` (1044) | names and lines read; see Reviewer notes on a length defect |

Rules for the import:
- The import is its **own PR** with `PROVENANCE.md` (source URL, pinned full commit SHA, kept, removed, changed) and a `NOTICE.md` entry, per AGENTS.md and RULES 17. The upstream `LICENSE` is copied next to the vendored files. The pin is the commit chosen at import time; this ADR records `015eaf8` as the commit inspected.
- Each kept function becomes a **pure function**: inputs are bytes, strings, keys and plain data objects; outputs are bytes or strings. Every `frappe.*` call (`get_doc`, `db.get_value`, `throw`, `publish_realtime`, `_`) is removed. Errors raise our own exception types.
- Everything not in the table is dropped: the clearance and reporting calls, the scheduler, the background queue, the PDF/A-3 module, onboarding API calls, DocTypes, fixtures, custom fields, Desk JS and CSS, workspaces, icons and the stub tests.
- Before the import PR, audit the transitive dependency tree of what is kept (`cryptography`, `lxml`, `asn1`) and record it in the licence register.

### 2. Rebuild ourselves
- **Hash chain and invoice counter allocator.** One chain per invoicing unit (the ZATCA EGS unit), in its own table, not custom fields on core records. Allocation takes a row lock on that unit's chain head, assigns the next ICV, computes the hash, signs, stores the new head and commits. The lock is held **only while hashing and signing**, never across a network call. A rejected invoice **stays in the chain**: its ICV and hash are not reused or rolled back; the correction is a new document.
- **Clearance and reporting outbox.** Signing and chain advance commit together with an outbox row. A separate worker submits standard invoices for clearance and simplified invoices for reporting, retries with backoff and is idempotent on the invoice UUID. It tracks the **24-hour reporting window** for simplified invoices and raises an alert before it lapses. The window length comes from the country pack (ADR-0015), not a constant.
- **All engine hooks.** Our own hooks in our engine app trigger signing on submit, block edits after issue, store the signed XML immutably and emit platform events (ERP-009, event stream contract BPL-011). Rejections reach users as our own error model in Arabic and English (ADR-0016). Nothing touches Desk.

Reason: the evaluation found stub tests, non-transactional chain writes and Desk coupling. We take none of that.

### 3. Process
ADR first, then build. CMP-004 is Tier 3 rigid-zone work (ADR-0031, ADR-0035): tests against official ZATCA vectors, line-by-line human review by a founder who did not prompt the code, accountant review of the tax figures, logged model and prompt. **The ZATCA sandbox run is the acceptance test** for CMP-004. Until it passes, say "implemented, not yet verified", never "compliant" or "certified".

### 4. Where the code lives (partner lane)
- Vendored code: `components/compliance/zatca_sa/vendor/erpgulf/`, with `PROVENANCE.md` and the upstream `LICENSE`. Nothing outside our Phase 2 package imports it directly.
- Our Phase 2 code (chain, counter, outbox logic, adapters over the vendored functions): `components/compliance/zatca_sa/phase2/`, next to the existing Phase 1 module, under the same `compliance.zatca_sa` manifest. The manifest records the upstream pin.
- Engine hooks and the chain and outbox tables: the engine app's compliance module, `apps/engine/change_engine/change_engine/compliance/`, which exists and is empty.

### 5. Tracking upstream security and correctness fixes
- `PROVENANCE.md` and the component manifest record the pinned SHA. Vendored files are never edited in place without a line in `PROVENANCE.md` "Changed".
- The partner watches the upstream repository's releases and security advisories. At each upstream release, and at least at every gate exit while this component is live, the partner diffs the kept upstream functions between our pin and the new commit and records the result in a session log: no relevant change, take the fix, or not applicable.
- Taking an upstream fix is its own Tier 3 PR that moves the pin, re-runs the official vectors and the sandbox suite (CMP-008 makes this automatic in G2; CMP-020 adds the regulation watcher in G4).
- Python dependencies of the kept code (`cryptography`, `lxml`, `asn1`) are covered by the repo's existing dependency scanning (`.github/dependabot.yml`, `.github/workflows/audit.yml`).

## Constraints this sets for CMP-004 (checklist)
- [ ] Vendoring import merged first, in its own PR with `PROVENANCE.md`, upstream `LICENSE`, `NOTICE.md` entry and transitive licence audit.
- [ ] No `frappe` import in vendored or `phase2/` code; the engine is reached only through our hooks and adapter.
- [ ] One hash chain per invoicing unit; ICV allocated from that chain under a row lock; never derived from the invoice name.
- [ ] Lock held only while hashing and signing; no network I/O inside the lock.
- [ ] Rejected invoices stay in the chain; no ICV or hash is reused, skipped or rewound.
- [ ] Chain advance and outbox row commit in one transaction; submission is a separate idempotent worker keyed on the invoice UUID.
- [ ] Clearance for standard, reporting for simplified; reporting window from the country pack; alert before it lapses.
- [ ] No tax computation in our code or in vendored code: every amount, VAT figure and rounding comes from the engine; our code formats, encodes, checks (fail closed) and transmits (ADR-0031 one calculation authority).
- [ ] Private keys never stored in engine records; key custody per threat model T10 (SEC-002, SEC-011).
- [ ] No Desk, realtime, GIF or engine-named output on any customer path (ADR-0016).
- [ ] Every conformance test uses a vector copied from ZATCA's own documents, SDK or sandbox, with URL and access date beside it (ADR-0031 condition 1).
- [ ] Line-by-line human review and accountant review recorded on the PR; session log keeps model and prompt (ADR-0031 conditions 2-4).
- [ ] ZATCA sandbox run passes: onboarding (CSR, compliance CSID, production CSID), standard clearance, simplified reporting, credit and debit notes, a rejection followed by recovery, a retry after timeout ([e-invoicing.md](../compliance/e-invoicing.md) sandbox plan).
- [ ] Concurrency test: parallel submissions on one unit produce one unbroken chain.

## Alternatives rejected
- **Fork the whole app:** inherits Desk coupling, custom fields on core records, the non-transactional chain, keys in records and the maintenance of a large codebase with no tests.
- **Rebuild from scratch:** wastes parts that already encode ZATCA's canonicalisation, signing envelope and QR rules, and re-learns their quirks the slow way.
- **Run the upstream app as-is behind a wrapper** (the evaluation's other option): the chain and Desk problems sit inside the app and a wrapper cannot fix them.

## Consequences
- Easier: CMP-004 starts from working crypto and XML structure; state, concurrency and error handling are ours and testable.
- Harder: we own the adapted code and its divergence from upstream; upstream fixes need a manual diff each time.
- Must be done: the vendoring import PR (partner, under CMP-004 or a new plan row if the founder prefers), then CMP-004; key custody (SEC-002, SEC-011) before any real key; engine event emitter (ERP-009). R-018 mitigation moves from "proposed" to this plan once accepted.
- CMP-033 stays `doing` until the partner accepts this ADR.

## Reviewer notes
Written by the drafting agent (Claude Opus 5.5). These do not change the decision above; the founder decides.

1. **The "pure core" is not pure.** At `015eaf8`, `sign_invoice_first.py` has 182 lines naming `frappe` and the XML builders take an engine `Sales Invoice` document. `digital_signature`, `certificate_hash`, `tag8_publickey` and the CSR functions look keys and certificates up from engine records by company abbreviation. "Vendor" will in practice mean "extract and adapt". The PROVENANCE "Changed" list will be long, and the Tier 3 review must cover the adapted code as if it were new.
2. **The XML builders compute tax.** `xml_tax_data.py` recomputes VAT (`net_amount * (tax_percent / 100)`, line 95; `taxable_amount * rate / 100`, lines 202 and 225) and rounds per element. `create_xml_final_part.custom_round` (line 1090) rounds a third decimal of exactly 5 down (`ROUND_DOWN`). That conflicts with ADR-0031 (one calculation authority; VAT rounded once at document level). Suggest: vendor only the element structure and namespaces of the builders, strip all arithmetic, and feed figures from the engine. Otherwise the import brings a second tax authority.
3. **The TLV encoder has a length defect for Arabic text.** `get_tlv_for_value` (line 954) takes the length of a `str` in characters, then encodes to UTF-8. Any multi-byte value, such as an Arabic seller name, gets a wrong length byte. Values of 256 characters or more get a non-standard `0xFF` prefix. Our Phase 1 encoder (`components/compliance/zatca_sa/phase1.py`, CMP-003) already measures UTF-8 bytes. Suggest: extend our encoder for tags 6-9 and do not vendor `get_tlv_for_value`. Defect found by reading; not run.
4. **Key generation is fine; key storage is not.** Keep the `SECP256K1` generation and the CSR OID encoding; drop the PEM-in-a-record storage (finding above).
5. **Facts the build must confirm (UNVERIFIED here):** that the 24-hour reporting window is the current rule ([e-invoicing.md](../compliance/e-invoicing.md) marks clearance and 24-hour semantics UNVERIFIED); that a rejected invoice's hash is the PIH of the next invoice; whether the PIH after a cleared standard invoice is the hash of our signed XML or of the cleared XML ZATCA returns; and that `digital_signature` signs what the ZATCA SDK signs. Each needs a citation to ZATCA's own guideline or SDK before CMP-004 closes.
6. **Placement.** `vendor/` sits inside the existing component so one manifest and one review cover Phase 1 and Phase 2. If the founders want vendored code kept out of `components/` entirely, `apps/engine/` is the alternative, but then the pure functions would sit next to engine code, which this ADR is trying to avoid.

## Open questions for the founder
1. Is the vendoring import part of CMP-004, or its own plan row (for example a new CMP row in G1, partner)?
2. Accept the narrowing in Reviewer notes 2 and 3 (no tax arithmetic, no upstream TLV), or vendor the builders whole and strip later?
3. Where do the chain and outbox tables live: the engine database (same transaction as invoice submit) or a separate compliance store? This ADR assumes the engine database through our own engine app.
4. Who is the accountant reviewer for the tax figures (ADR-0031 condition 3, LEG-019)?
5. Upstream pin: `v3.0.1` (tagged, older) or a `main` commit at import time (newer fixes, untagged)? This ADR leaves it to the import PR and records `015eaf8` as inspected.

## Supersedes
None. Applies ADR-0016, ADR-0031 and ADR-0035 to the ZATCA Phase 2 component; acts on the CMP-002 evaluation and R-018.
