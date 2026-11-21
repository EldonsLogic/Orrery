# Session log: inf-009-review-fixes

Date: 2026-11-21
Author: partner
Tool and model: antigravity / Gemini 4 Hydrogen
Plan IDs: INF-009

## Summary
Addressed Eldon's cross-model review (`Claude Fable 5.2`) and the partner coordinator's review notes (`Claude Opus 5.5`) on PR #225 (`feecac0`) for `INF-009` (Proposed `ADR-0052` and supporting architecture/open-question docs; Option B remains the recommendation).

## Files touched
- `docs/decisions/ADR-0052-isolated-browser-runner-placement.md`:
  1. Listed all four `PLAT-VPC` <-> `BR-VPC` boundary crossings (`GW <-> STREAM`, `CTL -> VM`, `CAP -> DSC`, `PROXY -> AUD`) with direction, initiator, mTLS (`S03`) authentication, and data class; replaced "zero network route" with "no route except these named endpoints"; added a dedicated `SEC-015` requirement in section 4 for each crossing and extended negative test (a).
  2. Corrected credential path (`UI -> GW -> STREAM -> guest`): explicitly placed `GW` and `STREAM` in the transient `C4` handling path (chosen over custom client-to-VM E2EE crypto to keep v1 session framing simple inside our VPCs while enforcing `SEC-015` no-body/no-trace/no-APM/no-crash-dump controls and buffer zeroing), and extended negative test (c) to `GW` and `STREAM` logs, traces, and crash dumps.
  3. Recorded capture provenance residual risk for in-guest `CAP` (kept inside the `S4` microVM rather than host-framebuffer + proxy-SNI capture because host pixels lack DOM masking semantics for `PI-023`/`PI-005` and `PROXY` cannot see full HTTPS URLs without breaking `Q-517` no-TLS-MITM); required `DSC` (`SEC-015` / `DSC-010`) to treat in-guest URL, timestamp, and hash as unattested, recompute SHA-256 on receipt, verify claimed host against `CTL`/`PROXY` allow-lists, and run server-side secret scrubbing + `L3` tagging.
  4. Replaced HTTP 3xx redirect re-validation with validating every `CONNECT`/SNI hostname and resolved IP address without TLS interception (consistent with `Q-517`), and added `0.0.0.0/8`, `fc00::/7` (IPv6 ULA), and IPv4-mapped IPv6 (`::ffff:0:0/96`) to the proxy deny list.
  5. Marked all search-summary figures (Firecracker `< 5 MiB` / `<= 125 ms`, Browserbase 1-browser-per-VM claim, and Chromium CDP flag risks) explicitly `UNVERIFIED`.
- `docs/architecture/isolated-browser-runner.md`: aligned section 1 diagram/text, section 2 boundary invariants (all four crossings, `CONNECT`/SNI proxy rules and expanded deny list, in-guest `CAP` residual risk + unattested `DSC` intake), and section 3 session lifecycle (transient `C4` path `UI -> GW -> STREAM -> guest`).
- `docs/open-questions.md`: updated `Q-515` ("no route except the four named boundary endpoints") and `Q-517` ("validating `CONNECT`/SNI and resolved IPs") wording for consistency with `ADR-0052`.
- `docs/log/2026-11-21-partner-antigravity-inf-009-review-fixes.md`: this session log.

## Decisions
- **G3-at-G0 drafting note (ADR-0035 item 6):** `INF-009` is a G3 plan row drafted while G0 still has open rows, done at the **partner founder's explicit request** to unblock `SEC-015` and `DSC-017` placement design; `ADR-0052` remains `Proposed` and no code was written.
- **Skipped numbering holders:** `ADR-0051` was skipped because it is held by the **partner's PR for `SEC-022`**, and `Q-514` was skipped because it is held by the **partner's `ERP-015` work** (clarifying the earlier `inf-009-browser-runner-placement` log's unattributed "`Q-514` left reserved" note without modifying that append-only log).
- **Credential path choice (review item 2):** Kept `GW` and `STREAM` in the transient `C4` path with `SEC-015` no-log/no-APM/no-dump controls + extended negative test (c), rather than custom client-to-VM E2EE input crypto.
- **Capture provenance choice (review item 3):** Kept `CAP` inside the untrusted guest (for DOM masking and full URLs without TLS MITM), documented the residual risk, and required `DSC` to treat in-guest URL/hash as unattested and cross-check `PROXY`/`CTL` allow-lists.

## Tokens or cost
Unknown.

## Next step
Eldon cross-model re-review of PR #225, then founder acceptance and security review (`RULES` 42) of Proposed [ADR-0052](../decisions/ADR-0052-isolated-browser-runner-placement.md), and resolve `Q-515`–`Q-519` / `Q-2` before `SEC-015` and `DSC-017`.
