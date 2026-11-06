# connectors

Status: draft
Owner: unassigned

Purpose: implementations of the [connector interface](../contracts/connector-interface.md): `describe`, `authorize`, `extract`, `normalise`, `map`, by capability tier.

Planned first connectors (order to confirm): `file.excel_upload` (tier 2), `file.csv_upload` (tier 2), document intake with Arabic OCR (tier 3), `inbox.email_forward` (tier 4). Tier 1 vendor APIs chosen from the pilot's actual tools. Tier 5 browser session only as a late fallback with its own ADR.

Each connector folder holds: manifest, schemas, anonymised sample files, tests, security review notes, licence record.

**Empty until gate G1** (one connector by G2).
