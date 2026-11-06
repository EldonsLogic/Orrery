# Access policy

Status: draft
Owner: eldon

| Area | Rule |
|---|---|
| Accounts | Individual accounts only; no shared logins; company identity provider for staff |
| MFA | Required for all staff on all systems (code host, cloud, secret manager, AI provider consoles, internal console); phishing-resistant method preferred |
| Least privilege | Roles per function; access requested with reason; reviewed every quarter; default deny |
| Production | No standing human access to production data. Changes by IaC and CI only. Break-glass account sealed, alerts on use |
| Support access | Just-in-time, time-boxed, ticket-linked, approved by a second person, tenant notified, every action logged, auto-expires. Read-only by default |
| Secrets | Held in a secret manager; per environment; never in repo, chat, tickets or prompts; rotated on staff change and on schedule; scanning in CI and pre-commit |
| AI agents | Agents work with scoped tokens, never founder-level credentials; no production credentials in dev tools; agent actions logged |
| Devices | Disk encryption, screen lock, OS updates for founders' machines; lost device procedure in [incident-response.md](incident-response.md) |
| Third parties | Approved processors only ([hosting-rules.md](hosting-rules.md)); access removed at contract end |
| Onboarding | Role assigned, MFA enrolled, policies read, access granted per role |
| Offboarding | Same-day removal of all access, key/secret rotation where the person had access, device return, access review log kept |
| Code repo | Protected main, PR review, CODEOWNERS, signed commits recommended |
| Review cadence | Access review each quarter; policy review at each gate |
