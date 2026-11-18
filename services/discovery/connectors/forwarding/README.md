# Forwarding intake (DSC-015), tier 4

Two read-only connectors, stdlib only (`email`, `html.parser`, `zipfile`), no network, no accounts: they parse bytes.

| Connector | Input | Output |
|---|---|---|
| `discovery.forward_email` | one RFC822 message | headers (sender and reply-to as PI-007 fields), body, quoted text, hidden HTML text, dates found in the body (Gregorian and Hijri, Umm al-Qura via the DSC-014 helper), attachment list |
| `discovery.forward_whatsapp` | exported chat `.txt` (UTF-8) | participants, messages with an `#meta` field (ISO time, calendar, media or system flag) |

Rules it enforces
- Everything goes through the DSC-010 runner: sanitise.py, L3 `untrusted` envelope, instruction-like flags. Text is data, never instructions. No recipient is derived from any header.
- Bidi, zero-width and control characters are stripped and flagged by the runner (also in filenames and subjects).
- Attachments are typed by content. Executables, scripts, shortcuts, macro Office files, HTML/SVG and archives are blocked. Default `strict=True` refuses the whole message (`FWD-002`); `strict=False` blocks the attachment and keeps the body. Allowed attachments are returned by `attachment_payloads(raw)` with a `route` (`discovery.intake` for PDF, PNG, JPEG, TIFF; `discovery.tabular` for XLSX, CSV); the caller runs each in its own `run_connector`.
- Dedup: `dedupe_messages` (Message-ID, or sender plus normalised subject plus body), quoted lines that repeat the body are dropped, WhatsApp repeats of (time, sender, text) are dropped. `thread_key` gives a thread id and content key.
- PII minimised: no logging in this package; refusal reasons and issue details carry codes and indexes, never addresses, names or filenames. Audit events come from the runner and hold hashes and counts.
- Dates: email `Date` keeps its offset; WhatsApp has none, so `timezone_unknown`. Day/month order is inferred over the whole chat, flagged when undecidable.

Not done: real mailbox or WhatsApp Business ingestion, SPF/DKIM/DMARC results (need the receiving MTA), zip-with-media exports, nested forwarded `.eml` parsing, OS isolation (logical sandbox only, see `model.py`). Tests: `services/discovery/tests/connectors/forwarding/`.
