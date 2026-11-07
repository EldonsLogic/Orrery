# ADR-0018: Development environments and progress viewing

Status: Accepted
Owner: eldon
Approved by: Eldon and partner

## Context
Both founders, and their agents, must always be able to see the product as it develops: not only read docs. Nothing runnable exists yet, so this decision is a plan, not a deployment. Constraints already settled: the engine is invisible to customers (ADR-0016), production data stays in-country (ADR-0006), secrets never enter the repo, the web stack is not yet chosen, identity (ADR-0007) is still Proposed.

## Decision
1. **Always viewable.** Progress is viewable from the earliest stage. A PR that changes visible behaviour says how to view it (preview link or exact steps) in its description.
2. **Web app (marketing site, chat and role screens): Vercel**, because every pull request gets a preview link both founders can open. The web stack is decided in a short ADR first (plan row WEB-018). The first thing hosted is the static design-system preview pages in `docs/brand`, then clickable chat screens.
3. **ERP engine and our AI and gateway services: one small shared dev server** (a cloud VM or a container host such as Fly, Railway, Render or DigitalOcean; choice pending), running `infra/dev/docker`, behind a login, from the first technical test (gate G1). The engine cannot run on Vercel (long-running Python, MariaDB, Redis, workers).
4. **No Supabase for now.** It is Postgres and does not fit the engine. Revisit when the platform's own database and sign-in are built, after ADR-0007.
5. **Synthetic data only on any dev host.** Production or pilot data never goes to dev. Dev hosts outside the country are allowed for synthetic data only; production data stays in-country (ADR-0006). Regions of Vercel and any dev host are unchecked.
6. **The engine stays invisible on dev previews too** (ADR-0016): the browser talks only to our web app and gateway.
7. **Secrets** (AI provider keys, hosting tokens) live in the hosts' secret stores, never in the repo.
8. **Agent rule.** When something needed to view progress does not exist (a Vercel project, the dev server, access, keys), the agent stops and asks the founders to create it, listing exactly what is needed and where the secrets go. It does not guess or work around it. The founders create the accounts and projects.

## Alternatives rejected
- Local-only viewing: one founder cannot see the other's work; no per-PR links.
- Putting the engine on a serverless web host: cannot run it.
- Adopting Supabase now: no fit with the engine; adds a second data store before the platform database is designed.
- Using real data on dev to look realistic: breaks residency and the data rules.

## Consequences
- New plan rows INF-012, INF-013, WEB-018, WEB-019, DAT-009, QA-017.
- hosting-rules gains a development-hosts section; the overview and infra docs point to it.
- Costs and account ownership (company versus personal) are open until the founders create the accounts.

## Supersedes
none
