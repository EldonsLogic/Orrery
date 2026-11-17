# Brand asset upload security

Status: draft
Owner: eldon
Approved by: pending (partner review with a different model; security review before SEC-006 starts)

Plan ID: SEC-018. Specifies the rules for tenant logos, favicons and any branding upload ([../product/theming-and-tenant-branding.md](../product/theming-and-tenant-branding.md), [ADR-0014](../decisions/ADR-0014-theming-and-tenant-branding.md), [../brand/12-tenant-theming.md](../brand/12-tenant-theming.md) sections 4, 5 and 9). Enforcement is built in SEC-006, on storage from PLT-017. Consumers: BRD-007 (asset pipeline), BRD-008 (favicon), WEB-007 to WEB-009 (settings, login, document templates), PLT-018 (Powered-by entitlement) and tests in QA-008 and the malicious corpus (section 12). Threat addressed: T17 in [threat-model.md](threat-model.md), plus tenant isolation (T38, T50) for the storage rules.

Nothing here is built. Every behaviour below is a design requirement, not a description of running code. Numbers marked "decision" are proposals, not facts, and are listed in section 14.

## 1. Scope and stance
- **In scope:** logo (light, dark, mark), favicon and icon set, login background images if the founders approve them (decision BD-9), and every file derived from them.
- **Out of scope:** documents and spreadsheets uploaded for Discovery or Operate (DSC-010, [prompt-injection-defence.md](prompt-injection-defence.md) S1), custom fonts (not accepted), attachments to business records.
- **Trust.** An uploaded brand file is untrusted content, trust level L3 in [prompt-injection-defence.md](prompt-injection-defence.md) section 2.1, however it is labelled. Its class is C2 until the tenant publishes it, then C0 ([data-classification.md](data-classification.md)). Its text content (SVG `<title>`, `<desc>`, text nodes, EXIF fields, file name) is data and is never given to a model as instruction. If a feature wants the model to look at the logo (for example to suggest colours), it receives only the re-encoded raster, tagged L3, and the colour values come back through deterministic code (AGENTS.md principle 6).
- **Layered.** No single control is trusted. Type checks, parsing, sanitising, re-encoding, scanning, isolation and safe serving each assume the others failed.
- **Claim.** These rules lower the chance that a hostile file reaches a user, an operator or a document. They do not prove a file is benign and do not replace the malware scanner or incident response.

## 2. Principles
1. Content decides type, never the name or the client (BAU-001).
2. The stored active asset is always a file the platform produced (re-encoded raster or re-serialised SVG), never the upload bytes.
3. Sanitise on upload and again treat the result as untrusted at render: restrictive headers, `<img>` only, separate origin.
4. Fail closed: scanner down, parser error, limit hit, storage error or audit write failure means rejected, not "probably fine".
5. The client is never a source of truth: type, size, hash, scan result and tenant come from the server.
6. Owner or admin roles only; the tenant comes from the session, never from the request ([action-policy-table.md](action-policy-table.md) principle 3).

## 3. Accepted content
| Format | Accepted | Notes |
|---|---|---|
| PNG | Yes | Non-animated only (APNG rejected) |
| JPEG | Yes | Baseline or progressive; CMYK converted to sRGB; no opaque-JPG derivation (theming doc section 4) |
| SVG | Yes | Static, sanitised, section 6 |
| GIF, WebP, AVIF, HEIC | No | Existing rule: only PNG, JPG, SVG. Animated formats are out; see decisions BD-1, BD-2 |
| ICO | No as upload | Favicons are generated, never uploaded as ICO; a custom favicon upload is PNG or SVG (decision BD-2) |
| PDF, EPS, AI, fonts, archives, Office files | No | Rejected by content sniffing |

| ID | Requirement |
|---|---|
| BAU-001 | Type is decided from content: leading magic bytes must match PNG (`89 50 4E 47 0D 0A 1A 0A`), JPEG (`FF D8 FF`) or a well-formed SVG root element, and a real decode must succeed with a pinned, sandboxed decoder. File extension and the client's `Content-Type` are ignored for the decision |
| BAU-002 | If the sniffed type, the extension and the client type disagree, the upload is rejected as a mismatch (no "fix up" by trusting one of them). The mismatch is audited |
| BAU-003 | Polyglots are rejected: a file that is valid as more than one format (for example PNG plus script, JPEG plus HTML, SVG plus HTML or ZIP) fails. Test: the decoder for the sniffed type must consume the whole file and the file must match no other signature in the sniff table |
| BAU-004 | Trailing data after the end marker (PNG `IEND`, JPEG `EOI`) or after the closing `</svg>` root (other than whitespace) is rejected, not trimmed, so a polyglot never reaches the re-encoder |
| BAU-005 | APNG (an `acTL` chunk), multi-frame or animated content, and interlaced or multi-image containers that the pipeline cannot reduce to one frame are rejected. SVG animation (`animate`, `set`, `animateTransform`, `animateMotion`) is stripped (section 6) |
| BAU-006 | An empty file, a file shorter than the smallest valid header, or a file with a null byte before the signature is rejected |

## 4. Size, dimensions, decompression bombs
Numbers are proposals from [../brand/12-tenant-theming.md](../brand/12-tenant-theming.md) section 4 where they exist; the rest are new. All are "decision" until the founders confirm (BD-3).

| Limit | Proposed value (decision) | Where checked |
|---|---|---|
| Max upload bytes, PNG or JPG | 2 MB | Streaming, before buffering the whole body |
| Max upload bytes, SVG | 200 KB | Same |
| Max pixel dimension, either side | 4096 px | From the header, before decode |
| Max total pixels | 16 million (4096 x 4096) | From the header, before decode |
| Min raster short side for a logo | 512 px (theming doc); the mark may be smaller, minimum 128 px | After decode |
| Max aspect ratio | 8:1 and 1:8 | After decode |
| Decode CPU time | 2 s, then kill | Sandboxed worker |
| Decode memory | 256 MB cap | Sandboxed worker |
| Decoded-to-compressed ratio | Reject above 100:1 unless dimensions are within the limits above (decision) | After header read |
| PNG metadata chunk total | 64 KB (text chunks are dropped anyway) | Parse |
| Uploads in flight per tenant | 2 | Gateway |

| ID | Requirement |
|---|---|
| BAU-010 | The size limit is enforced while streaming; a request that exceeds it is cut off and rejected, without relying on `Content-Length` |
| BAU-011 | Dimensions and total pixels are read from the header and checked before any pixel decode. A file whose header lies about its size is stopped by the decode time and memory cap |
| BAU-012 | Decoding and re-encoding run in a sandboxed worker with no network, no filesystem outside a scratch directory, a CPU time limit and a memory limit. A kill is a rejection, audited as "limit" |
| BAU-013 | Limits are configuration in one place, versioned, and returned in the rejection message (the limit, not the internals). Tenants cannot raise them |
| BAU-014 | Decoder libraries are pinned and patched on a stated cadence; a known-vulnerable version fails the build (supply-chain scan, SEC-005 if it covers images, otherwise a new plan row). Image decoder bugs are a real class (T17) |

## 5. Raster handling (PNG, JPG)
| ID | Requirement |
|---|---|
| BAU-020 | Every accepted raster is decoded and re-encoded by the platform to a new PNG (logos with transparency) or JPEG (photographic login backgrounds, if approved). The upload bytes are never stored as the active asset, never served, never embedded |
| BAU-021 | Re-encoding drops all metadata: EXIF (including GPS and camera serial), XMP, IPTC, comments, thumbnails, text chunks, and embedded colour profiles other than a normalised sRGB. Oddities (broken ICC, huge profile, profile with unusual tags) are discarded, not parsed further |
| BAU-022 | Orientation from EXIF is applied before the metadata is removed, so the logo is not rotated by the strip |
| BAU-023 | Output is normalised: 8-bit, sRGB, alpha kept, premultiplication consistent, no interlace, deterministic encoder settings so the content hash of the output is stable for the same input |
| BAU-024 | Re-encoding is not treated as proof of safety: the re-encoded output still goes to the scanner (section 7) and to the storage rules (section 8). OWASP notes that rewriting does not guarantee removal of all malicious content (verified, section 13) |
| BAU-025 | The upload page tells the user that location and camera data in the image is removed, in Arabic and English (i18n) |

## 6. SVG
Prefer raster where vector is not needed: documents, email and favicons use rasters generated from the sanitised SVG (section 9).

### 6.1 Parse and re-serialise
| ID | Requirement |
|---|---|
| BAU-030 | SVG is parsed with an XML parser configured to refuse DTDs and DOCTYPE, external entities, external DTD loading, XInclude, and entity expansion. A DOCTYPE is a rejection, not a strip. OWASP's XXE guidance says to disable DTDs where possible (verified, section 13) |
| BAU-031 | Processing instructions (`<?xml-stylesheet ...?>` and others other than the XML declaration) and comments are dropped. CDATA is converted to text |
| BAU-032 | The output is serialised from the sanitised parsed tree with a fixed namespace set. The upload text is never copied through, so a string-level trick (odd whitespace, encoding, mixed case, entity forms) cannot survive |
| BAU-033 | Encoding is UTF-8 only; other encodings are rejected. Names and values with control characters, bidi controls (U+202A to U+202E, U+2066 to U+2069) or a null are rejected (the text is data; bidi reordering is a documented trick, [prompt-injection-defence.md](prompt-injection-defence.md) S10) |
| BAU-034 | After sanitising, if no drawable element remains, or the result has a zero or invalid `viewBox`, the upload is rejected ("nothing safe remains") |

### 6.2 Allow-list (everything else is removed)
Elements (decision, BD-4 for the exact set): `svg`, `g`, `defs`, `path`, `rect`, `circle`, `ellipse`, `line`, `polyline`, `polygon`, `text`, `tspan`, `title`, `desc`, `linearGradient`, `radialGradient`, `stop`, `clipPath`, `mask`, `symbol`, and `use` only with a same-document fragment reference (`#id`).

Attributes (decision): geometry (`d`, `x`, `y`, `cx`, `cy`, `r`, `rx`, `ry`, `x1` to `y2`, `points`, `width`, `height`, `viewBox`, `preserveAspectRatio`, `transform`), paint (`fill`, `fill-opacity`, `fill-rule`, `stroke*`, `opacity`, `stop-color`, `stop-opacity`, `offset`, gradient units and transforms), text (`font-size`, `font-weight`, `text-anchor`, `direction`, `lang`), `id`, `clip-path` and `mask` with `url(#id)`, `class` (ignored by us). No other attributes.

| ID | Requirement |
|---|---|
| BAU-035 | Removed, with the removal recorded in the audit event: `script`, `foreignObject`, `iframe`, `embed`, `object`, `audio`, `video`, `canvas`, `a` (links), `image` (all, including `data:` images), `feImage`, `filter` effects that load resources, `style` elements, `animate*`, `set`, `handler`, `listener`, `font`, `font-face`, `cursor`, `metadata` and `switch` |
| BAU-036 | Removed: every `on*` event-handler attribute, `style` attributes, `href` and `xlink:href` except `#fragment`, `src`, any attribute not in the allow-list, and any attribute value containing `javascript:`, `data:`, `vbscript:`, `url(` pointing outside the document, `@import` or `expression(` after decoding entities and case folding |
| BAU-037 | `use` that references another file, a URL or a fragment that does not exist in the same document is removed. A `use` chain or loop (self-reference, mutual reference) is rejected |
| BAU-038 | CSS is not supported: no `<style>`, no `style=""`, no `@import`, no `url()` other than a fragment reference in `fill`, `clip-path`, `mask`. Colours come from presentation attributes only. This keeps the derived mono and reversed variants simple (theming doc section 4) |
| BAU-039 | Embedded fonts, base64 payloads and any `data:` URI are removed. Text that needs a font the platform lacks is a reason to ask the tenant to outline text, shown in the preview |
| BAU-040 | Limits (decision, BD-3): max 5,000 elements, max nesting depth 32, max 100 KB of path data in total, max 20,000 path commands per `path`, max 50 gradients, max 16 `use` instances in a chain depth of 1, max attribute length 8 KB. Over the limit means rejection, not truncation |
| BAU-041 | Sanitised output is re-parsed once and must be identical after a second pass (idempotence), or the upload is rejected. This catches mutation (mXSS) style differences between parse and re-serialise |
| BAU-042 | The sanitiser is a maintained library or a small in-house allow-list walker over a safe parser, chosen in SEC-006 with a written rationale. A deny-list-only sanitiser is not acceptable. Choice and version are recorded in each audit event (BAU-091) |
| BAU-043 | Sanitised SVG is the stored artefact. The platform never trusts it at render either: BAU-050 to BAU-054 still apply |

### 6.3 Serve and embed
| ID | Requirement |
|---|---|
| BAU-050 | Assets are served from a separate, cookieless origin (a registrable domain of its own, not a subdomain of the app, so cookies and storage never mix). No tenant session or token is ever sent there. CORS is off unless a named origin needs it |
| BAU-051 | Every response sets `Content-Type` ourselves (`image/png`, `image/jpeg`, `image/svg+xml`), `X-Content-Type-Options: nosniff`, `Cross-Origin-Resource-Policy` as decided by BD-8, and for SVG `Content-Security-Policy: default-src 'none'; style-src 'none'; sandbox` (no scripts, no resources). A browser may still render SVG opened directly, so CSP is a backstop, not the control |
| BAU-052 | `Content-Disposition` is `inline` only when requested through an `<img>` or CSS image context and `attachment` for any direct navigation where the request headers (`Sec-Fetch-Dest`, decision BD-7) show a document load. The filename in the header is our own hash-based name, never the client's |
| BAU-053 | The app embeds logos only with `<img>` (or CSS `background-image`), never inline SVG, `<object>`, `<embed>` or `<iframe>`, and never builds markup from SVG text. SVG inside `<img>` runs no script and loads no sub-resources, which is a browser behaviour (UNVERIFIED for every browser we support; test in QA-008) |
| BAU-054 | Asset URLs are content-addressed (hash in the path) with long immutable caching. There is no listing and no route that serves by user-supplied path |

## 7. Malware scan and quarantine
| ID | Requirement |
|---|---|
| BAU-060 | States are `received`, `quarantined`, `scanning`, `rejected`, `active`. A file is `active` only after type checks, sanitising or re-encode, and a clean scan of the platform-produced output. Nothing in `received`, `scanning` or `quarantined` is reachable from any tenant or public URL |
| BAU-061 | Scan the received bytes before parsing, and the produced output before activation. Either detection moves the file to `quarantined`, notifies the tenant owner with a generic message, and opens a Sev 3 ticket (Sev 2 on repeated hits from one tenant or a detection on the produced output, which means the pipeline was bypassed) |
| BAU-062 | Fail closed: if the scanner is down, times out, returns an error, has signatures older than the maximum age (decision BD-5, proposal 24 hours) or returns anything other than a clean verdict, the upload stays `quarantined` and the tenant sees "try again later". It is retried by a job. It never becomes `active` unscanned |
| BAU-063 | Scan verdicts come only from the scanner service, authenticated service to service. No field of the request, header or file can set, skip or influence a verdict |
| BAU-064 | The scanner service, its region and its data handling are on the processor list ([hosting-rules.md](hosting-rules.md), [../legal/checklist.md](../legal/checklist.md)). Uploaded files stay in the tenant's region (DAT-003) |
| BAU-065 | Errors to the tenant never name the scanner, its signature, its version or the engine verdict. They say "file rejected" or "we could not verify this file" with a reference id. Details live in the audit event and the operator view only |
| BAU-066 | Quarantined bytes are kept for investigation for a stated period (decision BD-5, proposal 30 days), in a separate bucket with no read path except the security operator role, then deleted |
| BAU-067 | The scanner is a defence against known malware. It is not expected to catch a crafted SVG or decoder exploit; BAU-030 to BAU-043 and BAU-012 carry that |

## 8. Storage isolation
Builds on [hosting-rules.md](hosting-rules.md) (separate storage prefix and per-tenant keys) and [data-classification.md](data-classification.md).

| ID | Requirement |
|---|---|
| BAU-070 | Each tenant has its own namespace and key prefix, derived from the tenant id in the session, never from the request. A read or write outside the caller's prefix is refused by the storage service and tested (T38, T50) |
| BAU-071 | Object keys are `tenant-prefix/content-hash.ext` (hash of the produced output). No part of a key, path or bucket name comes from user input, including the file name, display name or an upload header. The client file name is never stored in a path or used for lookups |
| BAU-072 | Buckets are private, encrypted at rest with per-tenant keys (hosting rules), no public ACL, no website mode, no object listing, no execute permission, no server-side includes or per-directory config on the store |
| BAU-073 | Access is by signed URL, issued by the gateway after a tenant and role check, valid for a short time (decision BD-6, proposal 5 minutes for private assets) and bound to the exact object. Published assets (C0, such as the login-page logo) are served through the asset origin with content-hash URLs; see BD-6 for whether the hash alone is acceptable as a capability |
| BAU-074 | A guessed or replayed URL for another tenant's object, an expired signed URL, a URL with a changed path or a stripped signature returns the same generic not-found response (no oracle for existence) |
| BAU-075 | Content hashes do not leak across tenants: two tenants uploading the same logo get separate objects under their own prefixes (no cross-tenant deduplication) |
| BAU-076 | Deleting a tenant deletes its brand assets, derived variants, quarantine copies and cache entries as part of offboarding, with the other tenant data ([data-retention.md](data-retention.md), brand assets row; runbook "Offboard, export and delete tenant" in [../runbooks/README.md](../runbooks/README.md)). A legal hold stops it ([data-retention.md](data-retention.md)). Replacing a logo keeps the previous version only as long as the apply and roll-back window needs (decision BD-6) |
| BAU-077 | CDN or cache purge on replace and on delete is part of the same job; deletion is not complete until the purge is confirmed |

## 9. Derived variants and the Blueprint
| ID | Requirement |
|---|---|
| BAU-080 | Dark and mono and reversed variants, favicon sizes (16, 32, 48, 180, 192, 512, maskable 512, 1024 per [../brand/12-tenant-theming.md](../brand/12-tenant-theming.md) section 5), document and email rasters are produced server-side only from the sanitised or re-encoded asset, never from the upload and never by the browser. BRD-007 and BRD-008 own the code; SEC-006 owns the gate |
| BAU-081 | Derived files are produced into the same tenant prefix, pass the raster rules in section 5 and the scan in section 7 again, and are audited as derived (with the parent hash) |
| BAU-082 | A custom favicon upload follows the same rules as a logo; the generated `favicon.ico` is built by us from a PNG (PNG-compressed entries), never accepted as an upload |
| BAU-083 | The theme and token resolver takes logo references only (`asset:...`), not files or URLs ([../../services/blueprint/tokens/__init__.py](../../services/blueprint/tokens/__init__.py), [../brand/12-tenant-theming.md](../brand/12-tenant-theming.md) section 9). A reference must resolve to an `active` asset in the caller's own tenant; anything else fails validation. A Blueprint can never carry a URL or bytes for a logo |
| BAU-084 | Tenant documents (tax invoices, quotes, PDF) and emails embed the raster derived in BAU-080 only: inline PNG or JPEG in the PDF, hosted PNG or inline attachment in email. SVG is never embedded in a PDF or email. The logo never enters the QR clear zone and never moves mandatory fields (theming doc section 6). The file name, alt text and document metadata use the tenant display name, escaped, never the upload's metadata |
| BAU-085 | Email logos use a signed or content-hash URL on the asset origin with `alt` set to the display name; no tracking parameters and no tenant secrets in the URL |

## 10. Access, audit, limits
| ID | Requirement |
|---|---|
| BAU-090 | Upload, replace, rollback and delete require an authenticated session with owner or admin role, CSRF protection and the branding permission; the check is deterministic code at the gateway. Agents may not upload or replace brand assets; at most they draft a suggestion that a human applies ([action-policy-table.md](action-policy-table.md), SEC-020). Changing or removing the Powered-by mark is a separate entitlement (PLT-018) |
| BAU-091 | One audit event per attempt, success or failure: actor, role, tenant, time, request id, source IP class, content hash of the upload and of the produced output, sniffed type, size, result (accepted, rejected with reason code, quarantined), scanner name and version and signature date, sanitiser name and version, a list of removed element and attribute names (names only, not values), limit hit if any. If the audit write fails the upload fails (fail closed) |
| BAU-092 | Audit events are C2, kept with the audit log ([data-retention.md](data-retention.md)). They hold no file bytes and no client file name beyond the sanitised display form (BAU-100) |
| BAU-093 | Rate limits and quota (decision BD-3): 10 upload attempts per tenant per hour, 3 per user per 10 minutes, 20 stored assets per tenant including derived variants, 20 MB total. Rejections count toward the limit so probing is slowed. Over limit returns a generic message with a retry time |
| BAU-094 | Repeated rejections (decision, 5 in an hour) raise an alert to the security operator without telling the tenant what triggered it |
| BAU-095 | Brand asset licence and rights terms (tenant warrants rights to the logo) are in the legal checklist ([../legal/checklist.md](../legal/checklist.md)); the upload screen shows them and records acceptance |

## 11. File names and messages
| ID | Requirement |
|---|---|
| BAU-100 | The client file name is data. It is never used in a path, key, header (`Content-Disposition`), log line unescaped, email subject, PDF metadata or HTML. If shown back to the user it is displayed as text, escaped, after Unicode NFC normalisation, with bidi controls (U+202A to U+202E, U+2066 to U+2069), zero-width characters, control characters, path separators and trailing dots or spaces removed, and truncated to 80 characters |
| BAU-101 | Arabic and other non-ASCII names are accepted for display (the product is Arabic first) and never reach a path. A name that normalises to empty is shown as a generic label |
| BAU-102 | Double extensions (`logo.png.exe`, `logo.svg.php`), a leading dot, `..`, `/`, `\`, a null byte, NTFS stream syntax (`:`), reserved device names and very long names do not affect anything, because the name is not used; they are still flagged in the audit event as "suspicious name" |
| BAU-103 | Rejection messages are generic, localised, and name only the user-fixable cause: type not allowed, file too large (with the limit), image too small (with the minimum), could not read the file, try again later. They never reveal the scanner, a parser error string, a stack trace, a storage path or an internal id other than the reference id |

## 12. Attack and test cases
These form the malicious corpus in QA (CI runs them on every change to the pipeline). "Expected" is the required outcome. Sample files are generated by a test script outside the repo or kept as tiny fixtures; no real malware is committed (a harmless test signature such as the EICAR string is used for scanner tests; EICAR use is UNVERIFIED here, confirm in SEC-006).

| # | Case | Expected | Req |
|---|---|---|---|
| A1 | PNG with a JavaScript or HTML payload appended after `IEND` | Rejected (trailing data), audited | BAU-003, BAU-004 |
| A2 | JPEG with an HTML or JS polyglot in a comment segment | Output re-encoded; comment gone; still scanned | BAU-021, BAU-003 |
| A3 | SVG with `<script>` and `onload=` on the root | Script and handler removed or the upload rejected if nothing safe remains | BAU-035, BAU-036 |
| A4 | SVG with `<image href="https://attacker.example/x.png">` and `<use href="https://...#a">` | External references removed; no network request during processing or render | BAU-035, BAU-037 |
| A5 | SVG with a DOCTYPE and entities (XXE reading a local file, and billion-laughs expansion) | Rejected at parse, within time and memory caps | BAU-030, BAU-012 |
| A6 | SVG with `<foreignObject>` holding HTML and an iframe | Removed | BAU-035 |
| A7 | SVG with `<style>@import url(https://...)</style>` and `style="background:url(...)"` | Removed | BAU-036, BAU-038 |
| A8 | SVG with `javascript:` in `href`, mixed case and entity-encoded (`jav&#x61;script:`) | Removed after decoding | BAU-036 |
| A9 | SVG nested 10,000 deep, or 100,000 elements, or a huge path | Rejected on limits | BAU-040 |
| A10 | SVG `use` loop (a references b references a) | Rejected | BAU-037 |
| A11 | SVG with animation (`<set attributeName="href">`, `<animate>`) | Removed | BAU-035 |
| A12 | PNG 30,000 x 30,000 px, tiny on disk (decompression bomb) | Rejected from header; no decode | BAU-011 |
| A13 | PNG with a valid small header and a lying large decoded body | Killed by the memory or time cap, rejected as "limit" | BAU-012 |
| A14 | ZIP or gzip bomb renamed `logo.png` | Rejected by magic bytes; never unpacked | BAU-001 |
| A15 | JPEG with GPS EXIF and a camera serial | Accepted; output has no EXIF, GPS or XMP (checked by reading the stored bytes) | BAU-021 |
| A16 | JPEG with a rotated EXIF orientation | Output upright, metadata removed | BAU-022 |
| A17 | File name `../../../etc/passwd.png`, and `logo.png\0.exe` | Stored under `tenant/hash.png`; name not in any path | BAU-071, BAU-102 |
| A18 | `logo.png.exe` and `logo.svg.php` with matching contents | Judged by content; name ignored; flagged in audit | BAU-001, BAU-102 |
| A19 | Arabic file name with RLO (U+202E) and zero-width characters | Display form stripped of controls; no effect on headers or paths; no reordering in the UI | BAU-100, BAU-101 |
| A20 | PNG bytes sent with `Content-Type: image/svg+xml` and extension `.svg` | Rejected as a mismatch | BAU-002 |
| A21 | Windows executable renamed `.png` | Rejected by magic bytes; not forwarded to the decoder | BAU-001 |
| A22 | Scanner service down or timing out | Upload stays quarantined, not active; generic message; job retries | BAU-062, BAU-065 |
| A23 | Scanner signatures older than the maximum age | Same as A22 | BAU-062 |
| A24 | Request carries `X-Scan-Result: clean` or a `scan` form field | Ignored; the verdict comes from the scanner only | BAU-063 |
| A25 | Tenant B requests tenant A's asset by guessing or copying the URL | Generic not-found; audited as a denied read | BAU-070, BAU-074 |
| A26 | Signed URL used after expiry, and with a modified path | Generic not-found | BAU-073, BAU-074 |
| A27 | Blueprint sets `logo.light` to `https://...` or to another tenant's `asset:` id | Fails validation | BAU-083 |
| A28 | Member (not owner or admin) uploads; and an agent-origin call uploads | Refused; audited | BAU-090 |
| A29 | 50 uploads in a minute from one tenant | Rate limited; later attempts still counted | BAU-093 |
| A30 | Open the stored SVG URL directly in a browser as a document | `attachment` or sandbox CSP; no script runs; `nosniff` present | BAU-051, BAU-052 |
| A31 | Tenant display name and logo alt text with markup | Escaped in app, PDF and email | BAU-084, BAU-100 |
| A32 | Tenant offboarding | All assets, variants, quarantine copies deleted and purged from cache; verified by listing | BAU-076, BAU-077 |

## 13. Sources and what is verified
- OWASP File Upload Cheat Sheet, https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html, accessed 2026-11-16. Verified as stated there: allow-list of types, do not trust the client content type and combine signature checks with other checks, generate random server-side file names, limit sizes, store outside the webroot or on another server, rewrite images to strip metadata (and that rewriting is not a guarantee), scan for malware, authenticate and authorise uploaders, protect against CSRF, guard against decompression bombs. The page does not address SVG specifically.
- OWASP XML External Entity Prevention Cheat Sheet, https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html, accessed 2026-11-16. Verified: disable DTDs where possible; if not, block external entities and cap expansion. It does not mention SVG; applying it to SVG is our inference.
- SVG-specific serving guidance (sanitise on upload with a maintained library, serve `image/svg+xml` with a restrictive CSP and `nosniff`, prefer `<img>`): only secondary sources were found by search on 2026-11-16, for example https://digi.ninja/blog/svg_xss.php and the svg-hush documentation at https://docs.rs/crate/svg-hush/latest. The OWASP project did not turn up an SVG-specific page in that search. Treat all SVG guidance in section 6 as UNVERIFIED against an authoritative source.
- UNVERIFIED: that `<img>`-embedded SVG blocks script and external loads in every supported browser version; that a sandbox CSP stops a directly opened SVG in each of them; that the proposed numeric limits suit real tenant logos; that the chosen sanitiser library resists mutation tricks (BAU-041 is our mitigation, not a proof); the EICAR test string being accepted by the chosen scanner.

## 14. Requirement map
| Requirements | Enforcement | Also touches | Verification |
|---|---|---|---|
| BAU-001 to 006 (type, polyglot) | SEC-006 | BRD-007 (calls the gate) | Corpus A1, A2, A14, A18, A20, A21 |
| BAU-010 to 014 (limits, bombs) | SEC-006 | PLT-017 (stream limits) | Corpus A9, A12, A13 |
| BAU-020 to 025 (raster) | SEC-006 | BRD-007 (variants), WEB-007 (upload notice) | Corpus A2, A15, A16; QA-008 visual |
| BAU-030 to 043 (SVG sanitiser) | SEC-006 | BRD-007 (mono, reversed derivation depends on allowed fills) | Corpus A3 to A11 |
| BAU-050 to 054 (serve, embed) | SEC-006, PLT-017 (origin) | WEB-007, WEB-008 (use `<img>` only) | Corpus A30; QA-008 |
| BAU-060 to 067 (scan, quarantine) | SEC-006 | INF (scanner hosting), LEG (processor list) | Corpus A22 to A24 |
| BAU-070 to 077 (storage) | SEC-006, PLT-017 | OPR offboarding job, DAT-003 | Corpus A25, A26, A32 |
| BAU-080 to 085 (variants, documents) | BRD-007, BRD-008 (code); SEC-006 (gate) | WEB-009 (templates), QA-008 (documents in RTL) | Corpus A27, A31; QA-008 |
| BAU-090 to 095 (access, audit, limits) | SEC-006 | WEB-007, PLT-018, SEC-020 | Corpus A28, A29 |
| BAU-100 to 103 (names, messages) | SEC-006 | WEB-007 (display), QA-008 (Arabic names) | Corpus A17 to A19 |
| BAU-005, 053, 084 (what the pages render) | | WEB-007, WEB-008, WEB-009 | QA-008 |
| Incident path | | Runbook "Brand asset incident (malicious upload)" (G2) in [../runbooks/README.md](../runbooks/README.md); [incident-response.md](incident-response.md) | Rehearsal (scenario "malicious upload" in incident-response) |

Incident path. A confirmed malicious file that reached `active`, or a detection on produced output (BAU-061), is Sev 2 under [incident-response.md](incident-response.md): contain (disable the asset, purge cache, suspend the tenant's branding upload), assess from the audit events (hash, tenant, time), look for the same hash elsewhere, notify the tenant owner, fix the pipeline and add the case to the corpus. The runbook itself is a G2 plan row and does not exist yet; this section is only the requirement it must satisfy.

## 15. Decisions needed
| # | Decision | Proposal | Why it matters |
|---|---|---|---|
| BD-1 | Animated or other formats (GIF, WebP, AVIF)? | Keep PNG, JPG, SVG only (existing rule). Revisit WebP only if a customer need appears | Each decoder is attack surface |
| BD-2 | Accept ICO for custom favicons? | No: PNG or SVG in, platform builds `favicon.ico` | ICO is a container with several images and a history of parser bugs (UNVERIFIED) |
| BD-3 | Numeric limits in sections 4, 6.2 and 10 | Table values | All are proposals, not measured against real logos |
| BD-4 | Exact SVG element and attribute allow-list, and whether any CSS is ever allowed | List in 6.2, no CSS | Too strict rejects real logos (gradients, text); too loose reopens the surface |
| BD-5 | Scanner signature maximum age and quarantine retention | 24 hours; 30 days | Fail-closed outages vs retention of hostile files |
| BD-6 | Signed URL lifetime, whether content-hash URLs for published assets count as sufficient access control, and how long the previous logo is kept | 5 minutes; hash URL for published C0 assets only; keep the previous version for the roll-back window | Privacy of unpublished assets vs login-page speed and caching |
| BD-7 | Use `Sec-Fetch-Dest` to choose `inline` or `attachment` | Yes, with `attachment` as the default when absent | Browser support is UNVERIFIED |
| BD-8 | `Cross-Origin-Resource-Policy` value on the asset origin | `cross-origin` for published assets (emails load them), `same-site` otherwise | Emails and tenant custom domains (PLT-022, G5) need to load assets |
| BD-9 | Login background images (theming doc open decision) | Not in scope until approved; same rules and a separate size limit if approved | Larger files, photos with metadata |
| BD-10 | Sanitiser: maintained library or in-house walker | Decide in SEC-006 with a written rationale and a test against the corpus | Library choice affects BAU-041 |

## 16. Open questions
1. Does the platform scan the produced raster only, or also the upload (BAU-061 says both)? Cost and latency are UNVERIFIED.
2. Which scanner, where is it hosted, and does any market's data-residency rule affect sending an upload to it? Processor-list entry needed ([../legal/checklist.md](../legal/checklist.md)).
3. Should a tenant on a custom domain (PLT-022, G5) serve assets from its own domain, and how does that fit the cookieless-origin rule?
4. How do we show a tenant what the sanitiser removed (names only, BAU-091) without leaking internals (BAU-103)?
5. Is the raster limit of 512 px minimum right for wide wordmarks (8:1 ratio)? A designer review is needed (theming doc says logo sizes need a designer).
6. Does the Powered-by mark (PLT-018) follow these rules? It is a platform asset, not an upload, so presumably it is trusted; confirm.
7. Who rotates and pins the decoder and sanitiser versions, and how fast after a published vulnerability (BAU-014)?
8. Should the same pipeline serve other tenant images later (product photos, staff photos)? Those need their own spec; this one covers brand assets only.

## 17. What remains
This is a first draft spec. Not done: partner review with a different model and a security review; choice of scanner, sanitiser and image library; measured limits against real Gulf and Egyptian logos; browser matrix tests for SVG in `<img>`; the corpus fixtures; the runbook (G2); the legal terms text; and an ADR if any rule here changes a contract. It claims no completeness: new decoder or browser behaviour, or a gap found in review, can add rules.
