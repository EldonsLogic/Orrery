# ADR-0052: Isolated browser runner placement (Tier 5 connector)

Status: Proposed
Owner: partner
Approved by: pending (cross-model review, then both founders; security review required by RULES 42 and connector-interface section 1)

Plan ID: INF-009. Design decision only; no code until this ADR is reviewed and accepted. Architecture diagram and boundary invariants: [../architecture/isolated-browser-runner.md](../architecture/isolated-browser-runner.md). Unblocks [SEC-015](../PLAN.md) (egress and credential controls) and [DSC-017](../PLAN.md) (Tier 5 browser session). Proposes the answer to open question `Q-2` in [../open-questions.md](../open-questions.md).

## Context

- [RULES.md](../RULES.md) rule 24 and [connector-interface.md](../../contracts/connector-interface.md) section 1 define Tier 5 as an **owner-driven, isolated, read-only browser session** used only as a late fallback when APIs, exports, OCR, and forwarding fail. It must **never store the owner's credentials** (no password or session cookie retained beyond the live session).
- [prompt-injection-defence.md](../security/prompt-injection-defence.md) (SEC-003) classifies Tier 5 web pages as trust source `S4` (highest prompt-injection exposure) and sets five mandatory requirements (`PI-020` to `PI-024`, plus attack case `A16`):
  - `PI-020`: No model-chosen navigation, typing, click, or download; the owner drives and the model reads captures.
  - `PI-021`: No access to tenant tools, the ERP engine, secrets, or other tenants; one session per owner, destroyed after use.
  - `PI-022`: Egress limited to owner-opened hosts and required page dependencies through a logging proxy; no reach to our private network or cloud metadata endpoints (`T18` in [threat-model.md](../security/threat-model.md)).
  - `PI-023`: No stored credentials, cookies, or session tokens beyond the session; model never sees credential fields; captures mask password inputs.
  - `PI-024`: Every capture is labelled L3 (`trust: "untrusted"`) with URL, timestamp, and hash, and passes `PI-004` (sanitisation) and `PI-005` (hidden text excluded and flagged).
- [threat-model.md](../security/threat-model.md) (`T22`, `T18`) and [risks.md](../risks.md) (`R-028`) flag credential leakage, SSRF/lateral pivot into the engine or shared Redis (`R-033`), and vendor ToS exposure.
- **In-country residency across four phase-1 markets ([ADR-0024](ADR-0024-four-phase-1-markets.md), [ADR-0006](ADR-0006-tenancy-site-per-tenant.md), [hosting-rules.md](../security/hosting-rules.md)):** Production tenant data stays in the tenant's country/region (`hosting-rules.md`, [data-classification.md](../security/data-classification.md)). Under [data-classification.md](../security/data-classification.md), captured ERP screens/exports are C2/C3 (unknown is C3 until classified) and live session credentials are C4. Legal transfer rules remain UNVERIFIED pending counsel (`LEG-003`/`LEG-012`), with notable cross-border friction documented in [egypt-research.md](../compliance/egypt-research.md) section 3 (Law 151 of 2020 cross-border permit risk, secondary sources, UNVERIFIED), [data-protection-and-residency.md](../compliance/data-protection-and-residency.md) (KSA PDPL M/19 & M/148 transfer rules, UAE FDL 45/2021, both UNVERIFIED), and [qatar-research.md](../compliance/qatar-research.md) section Q3 (Law 13 of 2016, sector localisation rules for regulated entities, UNVERIFIED).
- Cloud hosting providers are not yet chosen (`INF-001`, `Q-9`, `Q-129`). This ADR decides the **placement topology and isolation boundary** independently of any single cloud or browser vendor.

## Decision

### 1. Options evaluated

Four placement architectures were evaluated against the seven required criteria:

1. **Option A — Per-session disposable microVM/container in our in-country cluster:** Ephemeral KVM microVM (Firecracker/Kata class) or sandboxed container (gVisor class) running on dedicated tainted nodes inside the same regional cloud account and cluster as the platform/ERP runtime.
2. **Option B — Separate isolated cluster and cloud account per active region:** Dedicated, single-purpose cloud account/project and VPC/cluster in each active operating region (KSA, UAE, Egypt, Qatar as needed), executing each session inside a per-session disposable KVM microVM destroyed on exit, with zero network route and zero IAM trust back to the ERP/platform account.
3. **Option C — Managed remote-browser service (third-party SaaS):** External commercial browser cloud (e.g., Browserbase or Browserless Cloud) connected via API/WebRTC.
4. **Option D — On the owner's device:** Local browser extension or desktop helper running on the owner's own machine, streaming selected captures back to Discovery.

#### Evaluation matrix

| Criterion | Option A: In-country shared cluster | Option B: Separate isolated account/cluster per region | Option C: Managed remote-browser SaaS | Option D: On the owner's device |
|---|---|---|---|---|
| **Tenant isolation** (`PI-021`, `T3`) | **Medium-High** with KVM microVM; shared cluster/account increases blast radius if Kubernetes control plane, CNI, or node IAM is misconfigured or escaped | **Highest** — two independent boundaries: hardware microVM per session + separate cloud account/VPC/IAM perimeter with no route to engine, DB, Redis (`R-033`), or vault | **Low-Medium** — provider isolates sessions (e.g., Browserbase claims 1 browser per ephemeral VM: `https://docs.browserbase.com`, search summary 2026-11-21, exact architecture details UNVERIFIED), but relies on third-party multi-tenant control plane | **Low-Medium** — OS/browser profile mixes personal/corporate sessions, extensions, and local LAN; platform cannot enforce a clean single-session sandbox |
| **In-country residency** (`ADR-0006`, `ADR-0024`, `RULES 46`) | **Pass** — runs in the tenant's regional cluster | **Pass** — runs in the tenant's country/region (`INF-001` region) | **Fail** — Browserbase documents only `us-west-2`, `us-east-1`, `eu-central-1`, `ap-southeast-1` (`https://docs.browserbase.com/optimizations/latency/multi-region`, accessed 2026-11-21); none in KSA/UAE/EG/QA. Other SaaS providers in KSA/UAE/EG/QA are `UNVERIFIED` or absent; C3/C4 transit abroad | **Pass** — execution stays on owner's device in-country; captures upload directly to regional staging |
| **Credential non-storage** (`RULES 24`, `PI-023`) | **Pass** — owner types into live viewport; volatile RAM wiped on exit; requires strict gateway/node isolation so no node dump leaks C4 | **Pass** — volatile RAM only, zero disk persistence, zero `SecretStore` access, account holds no persistent secrets (`S05`–`S10`, `Z1`) | **Weak** — live credentials and session cookies pass through and exist inside third-party SaaS memory/infrastructure; requires trusting external ZDR claims | **Strongest** — credentials never leave the owner's machine |
| **Egress allow-listing** (`PI-022`, `T18`) | **Medium-High** — logging proxy enforced in namespace, but sits on the same VPC/network fabric as engine/platform services | **Highest** — dedicated VPC with no peering to `PLAT-VPC`; host firewall forces all microVM traffic through a dedicated logging egress proxy blocking RFC 1918, loopback, link-local/metadata, and platform CIDRs | **Weak** — limited to provider's proxy features; our logging proxy and SSRF/redirect rules cannot easily inspect or enforce inside third-party VPCs without double-proxying | **Fail** — cannot enforce server-side `PI-022` allow-list or block owner's local LAN/intranet access; relies on client OS/extension |
| **Session recording and audit** (`PI-023`, `PI-024`) | **Pass** — deterministic `CAP -> DSC` hash, timestamp, URL, proxy audit logs; password inputs masked before capture leaves VM | **Pass** — identical capture/audit guarantee, plus proxy/VPC flow logs sit in an isolated audit stream | **Weak** — provider-side replay/debugging logs risk capturing C4/C3 screens unless Zero Data Retention is contractually guaranteed and verified (`UNVERIFIED`) | **Weak** — client extension can be tampered with or bypassed; capture integrity and `PI-005` hidden-text checks must still run server-side without independent URL/fetch proof |
| **Prompt-injection exposure** (`PI-020`, `A16`) | **Pass** — model gets no CDP/browser control tools; only L3 sanitised captures reach `DSC` | **Pass** — same as A, plus even a browser renderer/kernel RCE triggered by malicious HTML/JS cannot pivot to engine or AI gateway | **Medium** — some managed services expose CDP endpoints by design; accidental CDP exposure or agent-control coupling raises `A16`/SSRF risk (`https://chromedevtools.github.io/devtools-protocol/` / Chromium `--remote-allow-origins` and `--user-data-dir` risks noted in search results 2026-11-21, exact Chromium release notes UNVERIFIED) | **Low-Medium** — malicious page runs in the owner's real local browser context (risk of local cookie/LAN interaction if not strictly isolated) |
| **Cost & operational burden** | **Lowest-Medium** — reuses `PLAT-VPC` cluster/ops; still requires microVM node runtime | **Medium** — one extra cloud account/VPC + egress proxy per active region; mitigated by identical `infra/` IaC and scale-to-zero on-demand nodes (G4 fallback only) | **Low ops, recurring vendor fee + legal/DPA overhead** — blocked by residency/processor approval (`hosting-rules.md`) | **Low cloud cost, high support/engineering burden** — cross-browser/OS extension maintenance, Chrome Web Store/Edge reviews, corporate firewall friction |

### 2. Technical isolation note (microVM vs userspace kernel vs standard container)

- Standard Linux containers share the host kernel and are rejected for untrusted browser rendering (browser renderers parse untrusted HTML/JS/fonts/media from arbitrary legacy ERPs).
- **Recommended guest boundary:** Hardware-virtualised **disposable microVMs** (e.g., Firecracker or Kata Containers over KVM) running one session per microVM. Firecracker provides KVM hardware virtualisation with a dedicated guest kernel and a minimal virtio device model designed to run workloads from different customers on the same physical machine (`https://github.com/firecracker-microvm/firecracker/blob/main/docs/design.md`, accessed 2026-11-21; Firecracker project documentation also reports `< 5 MiB` VMM memory overhead and `<= 125 ms` boot time at `https://firecracker-microvm.github.io/`, accessed 2026-11-21 via search summary — verify exact numbers on target `INF-001` hardware). Kata Containers wraps OCI containers in lightweight microVMs via CRI `shimv2` with pluggable VMMs (`https://katacontainers.io/`, accessed 2026-11-21).
- If an `INF-001` cloud provider does not offer nested KVM or bare-metal nodes in a given market, **gVisor** (`runsc` userspace Sentry kernel + Gofer filesystem proxy + Netstack + host `seccomp-bpf` allowlist, `https://gvisor.dev/docs/architecture_guide/security/`, accessed 2026-11-21) is the fallback container sandbox **only inside the isolated `BR-VPC` account** — never standard `runc` containers. No browser runtime vendor is chosen as final here.

### 3. Recommendation

**Adopt Option B: a separate, single-purpose isolated cloud account/project and VPC per active operating region, executing each Tier 5 session inside a per-session disposable microVM destroyed on exit** (illustrated in [../architecture/isolated-browser-runner.md](../architecture/isolated-browser-runner.md)).

Core placement rules:
1. **Separate account and VPC per active region (`BR-VPC`):** Activated per region (KSA, UAE, Egypt, Qatar) only when tenants in that region need Tier 5 (`DSC-017` is G4). Uses the same `infra/` IaC module as other environments (`hosting-rules.md`) with scale-to-zero / on-demand compute so idle regions incur minimal cost.
2. **Hard network & IAM isolation (`PI-021`, `T18`):** `BR-VPC` has **zero network route, zero VPC peering, and zero IAM trust** to `PLAT-VPC`, the ERP engine, MariaDB, Redis (`R-033`), `SecretStore` (`ADR-0038`), or ZATCA KMS keys (`Z1`). Only two authenticated mTLS channels cross the boundary:
   - `CTL -> BR-VPC`: session start/stop lifecycle (receives `session_id`, `tenant_id`, `region`, `max_ttl_s`; **never receives C4 user credentials or vault tokens**).
   - `CAP -> DSC`: unidirectional push of owner-triggered, masked, hashed L3 captures into the tenant's regional staging store.
3. **Owner-only control, no CDP exposure (`PI-020`, `PI-023`):** The owner interacts with a pixel/input stream relayed through our `ADR-0016`-compliant gateway. Raw Chrome DevTools Protocol (CDP) sockets are **never** exposed to the internet, the owner's browser, or any AI agent. Keystrokes and password inputs are never logged; password/OTP fields are masked before capture leaves the microVM.
4. **Mandatory logging egress proxy (`PI-022`):** MicroVMs have no direct internet route; all outbound traffic traverses a VPC-local logging proxy that resolves DNS independently, blocks RFC 1918 / loopback / cloud metadata / platform CIDRs, enforces HTTPS, re-checks redirects, and logs domains/bytes/blocks without logging passwords or response bodies.
5. **`INF-001` minimum floor caveat (`Q-515`):** If a regional cloud provider selected in `INF-001` does not support separate sub-accounts/projects, the minimum acceptable floor (requiring explicit founder sign-off in `Q-515`) is a **separate VPC/network perimeter and dedicated tainted microVM node pool** with zero route and zero IAM access to ERP/platform assets — never co-located on engine/application worker nodes.

### 4. What `SEC-015` must implement

`SEC-015` ("Egress and credential controls for the isolated browser runner", G3) must specify and test at least:
1. **Egress proxy enforcement (`PI-022`, `T18`):**
   - Block all direct container/microVM network egress except via the logging proxy.
   - Proxy resolves DNS (preventing DNS-rebinding TOCTOU) and denies RFC 1918 (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), loopback (`127.0.0.0/8`, `::1`), link-local / cloud metadata (`169.254.0.0/16`, `fe80::/10`, `fd00:ec2::254`), CGNAT (`100.64.0.0/10`), and our own `PLAT-VPC` / edge CIDRs; re-validate on every HTTP 3xx redirect.
   - Enforce HTTPS-only by default (explicit owner-confirmed exception if a legacy local-ish web ERP uses self-signed/TLS-only, never allowing unencrypted password submission silently) and host allow-listing seeded from the owner's target origin plus explicitly confirmed SSO/CDN hosts (`Q-517`).
   - Emit structured proxy audit events (`domain`, `port`, `bytes_out`, `bytes_in`, `allow|block`, `reason`) to the regional audit stream without recording URL query secrets, `Authorization` headers, cookies, or form bodies.
2. **Credential non-storage and masking (`PI-023`, `RULES 24`):**
   - Ephemeral RAM-only browser profile (`--user-data-dir` in tmpfs, never persisted to disk, shredded/destroyed with the microVM on close, idle timeout, or hard TTL).
   - Disable browser password manager, autofill sync, crash dumps/core dumps, and extension installs inside the guest image.
   - Mask `<input type="password">`, `autocomplete="current-password|new-password|one-time-code|cc-*"`, and sensitive headers (`Cookie`, `Set-Cookie`, `Authorization`) in `CAP` before any capture leaves the microVM.
   - Zero keystroke logging at the gateway, stream relay, and guest; continuous video recording disabled by default (`Q-516`).
3. **Capture boundary & anti-injection (`PI-020`, `PI-024`, `A16`):**
   - Unidirectional `CAP -> DSC` push over mTLS bound to `(session_id, tenant_id, region)` with strict payload size caps.
   - `DSC-010` boundary stamps `trust: "untrusted"` (L3), SHA-256 content hash, timestamp, and origin URL; runs `PI-004` sanitisation and `PI-005` hidden-text stripping/flagging before anything enters Discovery prompts or staging.
   - Confirm browser downloads triggered by the owner are either blocked in v1 or quarantined through malware scan + `INF-014` parser sandbox (`Q-519`).
4. **Hardening & kill-switch tests:**
   - Automated negative tests verifying: (a) microVM cannot reach `169.254.169.254`, `127.0.0.1`, RFC 1918, or `PLAT-VPC`; (b) a second session sees zero cookies/history/cache from a prior session; (c) password input values never appear in captures, logs, or events; (d) `A16` hidden-text injection on a web page triggers no model navigation or tool call.

## Alternatives rejected

- **Option A (In-country shared cluster):** Rejected as the primary target because sharing a Kubernetes control plane, CNI, or cloud account with the ERP runtime (`apps/engine`), Redis (`R-033`), and `SecretStore` increases the blast radius of a browser zero-day + runtime escape.
- **Option C (Managed remote-browser SaaS):** Rejected because major providers lack in-country regions across KSA, UAE, Egypt, and Qatar (e.g., Browserbase documents US/EU/Singapore only as of 2026-11-21), violating [hosting-rules.md](../security/hosting-rules.md) residency rules and placing live C4 credentials and C2/C3 ERP screens in third-party custody.
- **Option D (On the owner's device):** Rejected for v1 because the platform cannot enforce server-side `PI-022` egress allow-listing, guarantee a clean uncontaminated sandbox (`PI-021`), or prevent local tampering with `PI-024` capture provenance, while adding high cross-OS/extension support burden for two founders. May be revisited later only for regulated enterprise hybrid tiers.

## Consequences

- **Easier:**
  - Cleanest security story for `T18`, `T22`, `PI-021`, and `R-028` — untrusted third-party web pages render in a separate cloud account and disposable hardware-virtualised microVM with no path to production tenant DBs or signing keys.
  - Region-agnostic topology: `BR-VPC` uses one IaC template instantiated per active market region once `INF-001` chooses regional providers.
  - Unblocks `SEC-015` (G3) and `DSC-017` (G4) design work without committing to a browser vendor.
- **Harder:**
  - Adds one isolated account/project + VPC + logging egress proxy per active operating region where Tier 5 is enabled (mitigated by activating per region only on demand and scaling compute to zero when idle).
  - Requires streaming viewport/input securely through our gateway (`ADR-0016`) and building the `CAP` password-masking capture helper inside the guest image.
- **Must be done:**
  - `SEC-015` implements the egress proxy, credential non-storage, masking, and negative test suite defined in section 4.
  - `INF-001` verifies KVM / nested-virtualisation (or gVisor fallback) and multi-account support on shortlisted regional clouds (`Q-515`).
  - `DSC-017` implements the owner-driven session UI (`ADR-0016` compliant), attestation/ToS notice (`Q-518`), and capture intake into `DSC-010` staging.
  - Resolve founder open questions `Q-515` to `Q-519` in [../open-questions.md](../open-questions.md) and close `Q-2` once this ADR is accepted.

## Supersedes

None. Answers open question `Q-2` once accepted.
