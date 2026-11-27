# Data classification

Status: draft
Owner: eldon
Approved by: pending (partner review with a different model; counsel review of the personal-data rows under LEG-003)

Plan ID: DAT-001. Defines the classes, how a class is assigned, how each class is handled in each processing context, and which class every store and artefact carries. Retention and deletion are in [data-retention.md](data-retention.md). Residency per store is detailed later in DAT-003. Threats addressed include T49, T56, T58 and T59 in [threat-model.md](threat-model.md).

Nothing here is built. Every rule is a design requirement, not a description of running code. Legal points are UNVERIFIED until counsel reviews ([../compliance/data-protection-and-residency.md](../compliance/data-protection-and-residency.md)).

## 1. Classes
| Class | Name | Meaning | Examples |
|---|---|---|---|
| C0 | Public | Published on purpose by us or by the tenant | Marketing pages, public docs, status page, a tenant's published logo |
| C1 | Internal | Ours, not published, holds no tenant data | Repo docs, plans, architecture, system prompts, component library, synthetic and anonymised samples |
| C2 | Confidential | Tenant business data and anything derived from it | Ledger, invoices, stock, prices, customers and suppliers, Blueprints with tenant detail, chat transcripts, unpublished brand assets |
| C3 | Restricted | High-risk personal data and payroll | Employee records, salaries, national ID, residence permit and passport numbers, personal bank accounts and IBANs, health or family data in HR files |
| C4 | Secret | Material that grants access or signs on someone's behalf | E-invoice signing keys and certificate secrets, tenant encryption keys, API keys, connector tokens, session and support access tokens, passwords, one-time codes |

C4 is new: the earlier stub kept credentials and signing keys in C3. They are split out because their rules differ in kind (never exported, never sent to a model, never restored to another environment), not in degree.

**Personal-data tag (PD).** Class and personal data are separate questions. Any field that relates to an identifiable person carries the tag PD whatever its class. Ordinary business contact details (name, work phone, work email of a customer or supplier contact) are C2 + PD. PD triggers minimisation, data-subject requests and the deletion rules in [data-retention.md](data-retention.md). See decision D-1.

**Class is not trust.** The trust levels L0 to L3 in [prompt-injection-defence.md](prompt-injection-defence.md) say whether content may instruct the system. The class says who may see it and where it may go. A supplier email is L3 and C2; a system prompt is L0 and C1. Neither label changes the other.

## 2. Decision rule
Ask in order. The first "yes" sets the class.

| # | Question | Class |
|---|---|---|
| 1 | Does it grant access, decrypt or sign (key, token, password, certificate secret)? | C4 |
| 2 | Is it payroll, an HR record, a government identifier of a person, a personal bank account, or health, family or religious data of a person? | C3 |
| 3 | Did it come from a tenant, describe a tenant, or get derived from tenant data (including prompts, model outputs, embeddings, logs that carry tenant content)? | C2 |
| 4 | Is it ours and not published? | C1 |
| 5 | Was it published on purpose by its owner? | C0 |

1. **Mixed content takes the highest class** present. A transcript that quotes a salary is C3.
2. **Unknown is C3** until classified. Fail closed.
3. **Derived data inherits** the class, the PD tag, the tenant boundary and the region of its source: embeddings, memory, caches, search indexes, summaries, exports, backups.
4. **Aggregation can raise a class**, never lower it. Only the reviewed anonymisation step (DAT-008) lowers a class, and its output is C1.
5. **Classification is data, set by code.** Field classes ship with each component manifest and country pack. A model never assigns or lowers a class.

## 3. Handling rules per class
| Rule | C0 | C1 | C2 | C3 | C4 |
|---|---|---|---|---|---|
| Storage region | Any | Any approved company system | Tenant's region only ([hosting-rules.md](hosting-rules.md), ADR-0006) | Tenant's region only | Secret manager or KMS in the tenant's region; signing keys held separately |
| Encryption in transit | TLS | TLS 1.2+ | TLS 1.2+ | TLS 1.2+ | TLS 1.2+; never sent to a browser |
| Encryption at rest | Not required | Provider default | Per-tenant envelope key | Per-tenant envelope key plus field-level protection where the engine allows | Hardware-backed or managed KMS; never stored in a database field in clear |
| Who may access | Anyone | Staff and scoped agents | Tenant users by role and scope; no standing staff access | Tenant users with an explicit HR, payroll or finance role; no standing staff access | Services that need it, by identity; no human reads the value |
| Access logging | None | Standard | Every read through the Tool API and every staff access | As C2, plus alert on bulk reads | Every use and every administrative action, alert on anomaly |
| Support visibility | Yes | Yes | Just-in-time, ticket-linked, time-boxed, read-only, tenant notified ([access-policy.md](access-policy.md)) | As C2, masked by default; unmasking needs a stated reason and is logged per field | Never. Support can trigger rotation, not view |
| To a model provider | Yes | Yes, no secrets | Only through the AI gateway, approved provider, minimised (IDs and aggregates first) | Redacted or tokenised before the call unless the task needs the value and the tenant setting allows it; never national IDs or bank accounts in clear (D-2) | Never, in any form |
| In application logs and telemetry | Yes | Yes | Record IDs and counts only, no content | Never; masked at source | Never; scanners block it |
| In the audit log | n/a | n/a | References and payload hashes; content stays in the record | References only, values masked | Key or token identifier only |
| Evals and product improvement | Yes | Yes | Never raw. Only de-identified patterns under the contract's anonymised-reuse clause, promoted by a reviewed step ([../legal/checklist.md](../legal/checklist.md), DAT-008) | Never, not even de-identified, without a new decision | Never |
| Export | Free | Staff only | Tenant owner or delegated admin, audited, short-lived link (DAT-006) | As C2, with step-up authentication; included in tenant export | Never exported. Tenant gets its data, not our keys; its own e-invoice credentials are re-issued, not copied |
| Deletion | Unpublish | Normal housekeeping | Per [data-retention.md](data-retention.md) | Shortest period the law allows, per [data-retention.md](data-retention.md) | Destroyed on rotation, on tenant deletion and as the crypto-shredding step |
| In the repo | Yes | Yes | Never | Never | Never (secret scan in CI and pre-commit) |

## 4. Class by processing context
"Yes" means allowed under the section 3 rules. "No" is absolute.

| Context | C0 | C1 | C2 | C3 | C4 |
|---|---|---|---|---|---|
| Production, tenant's region | Yes | Yes | Yes | Yes | Yes, in KMS or secret manager only |
| Dev, staging, preview hosts | Yes | Yes | No. Synthetic data only (ADR-0018) | No. Synthetic only | Own per-environment secrets only; never a production secret |
| Founder and developer machines | Yes | Yes | No | No | Own development credentials only |
| Model provider through the AI gateway | Yes | Yes | Minimised, approved provider and endpoint, no training, zero or minimum retention | Redacted or tokenised by default (D-2) | No |
| Any model or AI tool outside the gateway (coding assistants, chat tools) | Yes | Yes, no secrets | No | No | No |
| Backups | n/a | Yes | Yes: per tenant, encrypted, same country, same class | Yes, same as C2 | Keys are backed up by the KMS, separately from data backups; a data backup never contains its own key |
| Support session | Yes | Yes | Just-in-time, read-only | Masked; unmask per field with reason | No |
| Application logs, metrics, traces | Yes | Yes | IDs only | No | No |
| Third-party processors | Yes | Listed tools only | Only processors on the approval list, up to their approved class ([hosting-rules.md](hosting-rules.md)) | Only where the list says C3 | Only the KMS and secret manager providers |
| Cross-tenant use (library, benchmarks) | Yes | Yes | Only after anonymisation output becomes C1 (DAT-008) | No | No |

Dev hosts get synthetic data only. Production or pilot data never goes to a dev host, a laptop, an eval set or a prompt used for development. Anonymised samples must be reviewed before they count as C1.

## 5. Tenant-level overrides
The platform ships the classes and rules as a floor. A tenant may tighten. A tenant may never loosen. Changing any override is a configuration action under [action-policy-table.md](action-policy-table.md) and is logged.

| Allowed (tightens) | Not allowed (loosens) |
|---|---|
| Raise a field or document type to a higher class | Lower any class or remove a PD tag |
| Switch off model processing for C3, or for named record types | Send C4 to a model, or C3 national IDs and bank accounts in clear |
| Require owner approval for every support session; block unmasking | Give staff standing access or skip the tenant notification |
| Shorter retention for data with no statutory minimum | Shorten a statutory retention period or delete under legal hold |
| Stricter export: two approvers, step-up, named recipients | Export C4, or export without an audit record |
| Opt out of anonymised reuse where the contract allows (D-5) | Store data outside the tenant's region, or move region outside a controlled migration |
| Longer audit-log retention | Disable audit logging, encryption, or tenant isolation |
| | Put real data on a dev or preview host |

## 6. Assignment table
Every store and artefact kind has one class. A new store or artefact needs a row here before it ships.

| Store or artefact | Class | PD | Notes |
|---|---|---|---|
| General ledger, journals, tax and VAT records | C2 | Sometimes | Statutory retention applies; immutable once posted |
| Issued e-invoices, credit and debit notes (signed XML, rendered PDF) | C2 | Yes (buyer details) | Immutable archive; statutory retention |
| E-invoice signing keys, certificate secrets, tax-authority API credentials | C4 | No | Held separately from other keys, stricter access |
| Tenant encryption keys, gateway provider keys, connector tokens | C4 | No | One key set per tenant and per environment |
| Payroll runs, payslips, wage-protection files, end-of-service calculations | C3 | Yes | |
| Employee master data, national IDs, residence permits, personal bank accounts | C3 | Yes | Masked by default in UI, support and logs |
| Customer and supplier master data, business contacts | C2 | Yes | C3 if a government identifier of a person is stored |
| Stock, prices, purchase and sales documents | C2 | Sometimes | |
| Blueprint drafts and published revisions, tenant configuration | C2 | Rarely | A generalised pattern with no tenant detail is C1 only after DAT-008 |
| Component library, country packs, system prompts, role specs | C1 | No | |
| Tenant brand assets | C2 before publication, C0 after | No | Upload rules in [brand-asset-upload-security.md](brand-asset-upload-security.md) |
| Uploaded documents, attachments, connector imports | Highest class of content; C3 until scanned and classified | Often | Always trust level L3 |
| Chat transcripts, prompts sent to models, model outputs, agent run records | Class of the data they carry, at least C2 | Often | Logged per tenant, in region |
| Per-tenant memory, embeddings, search indexes, caches | Class of source, at least C2 | Often | Never crosses tenants; deleted with the tenant |
| Audit log (postings, configuration changes, AI actions, support access) | C2 | Yes (actor identity) | Append-only; holds references and hashes, not C3 values |
| Application logs, metrics, traces, cost and usage records | C1 by design | Minimal (user and tenant IDs) | If tenant content leaks into a log, the log is the class of the leak and it is an incident |
| Support tickets and support session records | C2 | Yes | Screenshots and pasted data follow the mixed-content rule |
| Customer messages: inbound and outbound text, template params ([connector-messaging](../../contracts/connector-messaging.md) section 11) | C3 until classified, then C2 or C3 | Yes | Always L3 inbound; free text follows the mixed-content rule; transcript retention, expiry open (D-10); production held until LEG-003 and LEG-012 |
| Messaging consent records and contact keyed hashes ([connector-messaging](../../contracts/connector-messaging.md) section 6) | C2 | Yes | Append-only; kept while the contact exists plus the audit minimum |
| Support access tokens, break-glass credentials | C4 | No | Auto-expiring |
| Backups and tenant exports | Class of the highest data inside (C3) | Yes | Same country, encrypted, per tenant |
| Deletion certificates and tombstones | C1 | No | Hold tenant ID, hashes and dates only |
| Platform account, sign-up and billing records about tenants | C2 | Yes | Here the company is the controller, not the tenant |
| Website analytics | C1 | Possibly | Whether this is a transfer is open ([../compliance/data-protection-and-residency.md](../compliance/data-protection-and-residency.md) item 6) |
| Synthetic test and demo data, reviewed anonymised samples | C1 | No | The only tenant-like data allowed outside production |
| Eval sets and golden files | C1 | No | Built from synthetic data only |

## 7. Standing rules
- Real customer data never enters the repo, evals, or prompts used for development.
- Tenant data does not leave the tenant's region except under a documented, approved mechanism (legal position UNVERIFIED, LEG-012).
- Exports and backups carry the class of their source.
- A classification mistake that exposed data is handled under [incident-response.md](incident-response.md).
- This table is reviewed at each gate and whenever a store, processor or component is added.

## 8. Decisions needed
| # | Decision | Proposed default |
|---|---|---|
| D-1 | Accept the PD tag approach: business contact details are C2 + PD, not C3 (the stub listed phones under C3) | Accept; otherwise most sales records become C3 and masking makes the product unusable |
| D-2 | May C3 values ever reach a model provider in clear, and for which markets | No by default; per-tenant opt-in only after LEG-012, never for national IDs or bank accounts |
| D-3 | Accept C4 as a fifth class, split from C3 | Accept |
| D-4 | Is the audit log allowed to hold actor names, or only user IDs resolved at read time | IDs only, resolved at read time, so a later erasure does not need an audit rewrite |
| D-5 | Can a tenant opt out of anonymised reuse, and is C3 excluded from it permanently | Opt-out allowed if the contract template says so (LEG-013); C3 excluded |

## 9. Open questions
1. Does field-level encryption for C3 work inside the engine without breaking search and reports? Needs a spike before G2.
2. Which C2 record types hold personal data of buyers that a data-subject request could reach inside an immutable e-invoice? See [data-retention.md](data-retention.md) section 6.
3. Are payroll and HR data a "sensitive" category under each market's law with extra duties (consent, impact assessment, local storage)? UNVERIFIED for all four markets.
4. Does a model provider's abuse-monitoring retention count as a copy of C2 data outside the region? Depends on LEG-012.
