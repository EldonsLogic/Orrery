# ADR-0047: MFA design (TOTP now, step-up, recovery, throttling, session binding)

Status: Proposed
Owner: eldon
Approved by: pending (Tier 3 security ADR: the partner's review is required; security review per AGENTS.md)

## Context
SEC-005 (PR #186, merged) built MFA in `services/control-plane/identity/mfa/`. AGENTS.md says auth changes need an ADR and security review; Q-250 says SEC-005 is not done until this ADR exists. The PR #186 review and the Opus re-review (Q-251, Q-254) left residuals. [ADR-0007](ADR-0007-identity.md) items 1, 6 and 12 set the frame (MFA mandatory for admin, finance and accounting functions and all staff; passkeys; break-glass with delay). [ADR-0027](ADR-0027-human-floor-action-policy-and-agent-authority.md) and `docs/security/action-policy-table.md` require step-up on R3 and R4 approvals. [ADR-0035](ADR-0035-risk-tiered-review.md) makes auth Tier 3. This ADR records what is built and decides what is still open. No sign-in or bootstrap route may be exposed before the follow-ups below close.

## Decision
**1. Scope: who needs MFA.** Staff realm: always, no exceptions. Customer realm: roles with `isAdmin`, the functions finance, accounting, owner and support (`policy.MFA_FUNCTIONS`), and any member when the owner turns on "MFA for all". Checked at token issue and at role grant. A token carries `mfa` and `auth_time`; nothing else is trusted.

**2. Factors.** TOTP only for now (RFC 6238, SHA-1 default, one step of drift, replay refused by a compare-and-set last-used counter, secrets sealed by an AEAD `SecretBox` bound to realm, subject and factor id) plus single-use recovery codes (10 symbols, per-code salt, PBKDF2-HMAC-SHA256 with no early exit). Up to 3 factors per subject. WebAuthn/passkeys are the next factor and the preferred one for staff and owners; the interface (`webauthn.py`) exists, nothing implements it, and any non-TOTP kind is refused until an implementation is registered and reviewed (follow-up F1).

**3. Sign-in.** Password, then factor, in one call. Every failure is the same IDN-060 and the factor work runs whether or not the password was right, so neither answer nor timing confirms a password. Membership or staff state (IDN-009/010/011) shows only after password and factor both match. A success mints a token with `mfa=true`, `auth_time=now`.

**4. Owner approvals and step-up for Tier 3 actions.** "Step-up" means an MFA sign-in within `STEP_UP_MAX_AGE` (300 s); refresh keeps the old `auth_time`, so a refreshed session cannot step up. Needed today for: owner "MFA for all", support-grant approve and revoke, adding a second factor, removing a factor, recovery regeneration, every staff factor change. Needed by policy (not yet built) for R3 and R4 approvals in the action-policy table, bank-detail changes, permission and role changes, agent limit changes, Blueprint publish and C3/C4 export. Step-up is a gate on the approver, not a substitute for the approval binding in ADR-0027 and ADR-0032. Decision: step-up for those approvals must be single-use and bound to the action id and payload hash (follow-up F2; today it is a time window only, Q-155).

**5. Enrolment and recovery.**
- First customer factor needs proof of the password now: a session with `auth_time` inside 300 s, or the password re-entered at enrolment.
- First staff factor needs an admin-issued, single-use bootstrap ticket with a 1 h TTL, attempt-counted, failures as IDN-060. Who issues it: two staff, never the subject (placeholder, Q-221; confirm).
- Recovery codes are the recovery path for a customer who lost the device. A subject with no factor whose role needs MFA stays blocked (IDN-013). Owner break-glass with delay and notice to other admins (ADR-0007 item 12) is not built and is follow-up F3. Never SMS-only recovery for MFA-mandatory users or staff.
- Removing the last factor is one atomic store write that refuses if any of the person's tenants demands MFA.

**6. Rate limits.** Defaults (placeholders, tune with real traffic): 5 failures per 900 s window, 900 s lockout. Wrong passwords count per (subject, source); an injected `SourceThrottle` limits each source; the account key counts only attempts whose password verified, so a stranger cannot lock the owner out. Store, sealing and provider failures deny (IDN-064) and are not counted as guesses. Reference point: NIST SP 800-63B-4 allows up to 100 consecutive failures per authenticator and requires one-time use of an OTP while valid (https://pages.nist.gov/800-63-4/sp800-63b.html, accessed 2026-11-20, first 100000 characters read only; UNVERIFIED for the exact wording and section numbers). Our limits are far stricter, but fixed-window counting still allows about 480 TOTP guesses a day once the password is known (Q-254); F5 adds escalating back-off.

**7. Session binding.** Any change of a subject's active factors ends every session of that person in every tenant (or the staff member's) by bumping the session version, and `mfa_enrolled` is re-derived from active factors. Access tokens live minutes, refresh rotates with reuse detection (ADR-0007 item 10). A kept token stops at expiry.

**8. Phishing resistance.** TOTP is not phishing-resistant. NIST SP 800-63B-4 says AAL2 verifiers must offer a phishing-resistant option and AAL3 requires it (same URL, accessed 2026-11-20, UNVERIFIED section numbers). Decision: staff and owners move to WebAuthn as their required factor before the first real tenant (G3 per `docs/security/security-baseline.md`); TOTP stays as fallback for other members. WebAuthn Level 2 is the W3C Recommendation to target (https://www.w3.org/TR/webauthn-2/, not fetched, UNVERIFIED, accessed 2026-11-20).

**9. Residuals N1 to N5 (Q-254) as explicit follow-ups.** All five block any sign-in route.
- **N1** Password guesses count only per (subject, source) and `SourceThrottle` is optional: many sources give no cap per account. Follow-up: make a gateway-supplied `SourceThrottle` required, add a per-account password-guess ceiling that slows (back-off, not lock) without letting a stranger lock the owner out. Owner: eldon, G2.
- **N2** The session bump rewrites whole membership and staff rows from an earlier read, so a concurrent suspension or deactivation can be undone. Follow-up: a compare-and-set that increments `session_version` only (the support-grant `transition_grant` pattern).
- **N3** While locked, the right password gets IDN-061 and a wrong one IDN-060. Decision: check the lock before the password and answer IDN-060-equivalent for both; this reverses Q-251(b), whose reasoning fails because step-up, confirm and the enrolment password check also lock the account.
- **N4** The enrolment password check counts on the account key before verifying, so a stolen stale session can keep the owner locked out. Follow-up: count it on the (subject, source) key until the password verifies, like sign-in.
- **N5** A failure after the factor write leaves sessions alive and `mfa_enrolled` stale. Follow-up: one transaction for the factor write, session bump and flag; failing that, a repair step that runs first and denies until it completes (fail closed). Same as Q-251(g).
- Still open from Q-251 and Q-222: (a) extra attempt-store write timing, (c) no factor plus MFA role (F3), (d) attempt-row expiry, (f) notice to the person on lockout or factor change (F4), atomic store methods, KMS-backed `SecretBox`, shared attempt store, KDF tuning.

## Alternatives rejected
- SMS or email codes as a factor: SIM-swap and phishing exposure; ADR-0007 item 12 already bans SMS-only recovery for mandatory-MFA users.
- Provider-only MFA with no platform rules: the provider spike is open (ADR-0007 item 5); policy, step-up and session binding stay ours either way, and the ports keep the provider replaceable.
- Hard lock on wrong password per account: lets a stranger lock the owner out (N1, N4).
- Time-window step-up only for R3/R4 approvals: a stolen live session approves anything for five minutes; action-bound step-up (F2) is required.
- Waiting for passkeys before shipping TOTP: delays G2; TOTP is the fallback anyway.

## Consequences
- Easier: one documented rule set for every auth change; reviewers can check Q-254 closure against this list.
- Harder: step-up becomes per action (F2), every approval path must call it; staff and owners must carry a WebAuthn device.
- Follow-ups (rows to be added by the owner of SEC-005; none added here): F1 WebAuthn implementation, F2 single-use action-bound step-up, F3 owner and staff break-glass recovery with delay and notice (Q-221), F4 notices on lockout and factor change, F5 escalating back-off, N1 to N5 fixes, real store, KMS `SecretBox` and shared attempt store (Q-222).
- Plan: SEC-005 shows `done` but Q-250 says keep it open until this ADR is accepted. Decision for the founders: reopen it, or add a row; this ADR does not edit `docs/PLAN.md`.
- Placeholders to confirm: all numbers in sections 4 to 6. External facts are UNVERIFIED as marked.

## Supersedes
None. Implements ADR-0007 items 1, 6 and 12 for SEC-005; feeds ADR-0027 step-up.
