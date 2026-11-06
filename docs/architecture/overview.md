# Architecture overview

Status: draft
Owner: eldon

Five parts, four contracts, one engine behind an adapter. Decision: ADR-0003. Strategy basis: [strategy 04](../strategy/04-architecture-and-seed.md). Specs: [01](../specs/01-discovery.md), [02](../specs/02-blueprint-and-library.md), [03](../specs/03-erp-runtime.md), [04](../specs/04-operate.md), [05](../specs/05-platform.md).

## Diagram
```
                       Owner / staff (Arabic or English, light or dark, tenant-branded)
                                         |
                              +----------v-----------+
                              |  web/app  (one chat + role-based views)  |
                              +----------+-----------+
                                         |
 +---------------------+   +-------------v-------------+   +-------------------------+
 | [1] DISCOVERY       |   | [4] OPERATE               |   | [5] PLATFORM            |
 | interview, templates|   | intent router (discover/  |   | tenants, identity, plans|
 | connectors, gaps,   |   | ask/act/change), tool API,|   | metering, AI gateway,   |
 | visual Blueprint,   |   | semantic layer, approvals,|   | team console, support   |
 | quote               |   | agents, memory            |   | observability, flags    |
 +----------+----------+   +------+------------+-------+   +-----------+-------------+
            |                     |            |                       |
   (1) Blueprint            (3) Tool API   (4) Events  <---------------+
            |                     |            ^
 +----------v---------------------v------------+-----------------------------+
 | [2] BLUEPRINT & LIBRARY (the spine)                                         |
 | schema, validator, compiler, change engine (diff/apply/rollback), simulator |
 | component registry + certification, component factory, reuse metrics        |
 +----------------------------------+------------------------------------------+
                                    | (2) Component manifest
                          +---------v----------+   engine adapter
                          | [3] ERP RUNTIME    |<--------------------- country packs
                          | Frappe + ERPNext   |   (KSA, UAE, Egypt)
                          | site per tenant    |   ZATCA (MIT ERPGulf app)
                          +--------------------+
 Contracts (in /contracts): (1) Blueprint schema (2) Component manifest (3) Tool API (4) Event stream
 + Connector interface + Build states
```

## Settled cross-cutting decisions
- **Engine is invisible** (ADR-0016): headless and internal; our gateway and web app are the only customer-facing surfaces; nothing customer-visible names the engine.
- **Three markets** (ADR-0015): KSA, UAE, Egypt as certified country packs; Gregorian storage with Hijri as a display, entry and rule layer; per-company week, hours and fiscal settings with country defaults.
- **Theming** (ADR-0014): light and dark; tenant logo and primary colour within contrast guardrails; legal invoice layout wins.
- **Change engine** (ADR-0013): the engine-side apply layer of Part 2 lives in `apps/engine/change_engine/`; AI planning stays in separate services behind the gateway.
- **One chat, role-based views** (ADR-0004); human review gate and free-first with entitlements (ADR-0005); isolated tenant per customer (ADR-0006).

## Built versus planned
Built: contracts (specifications), the change-engine apply layer, the design system, docs, CI and checks. Planned (not built): engine bench and tenant creation, validator, compiler, Discovery, Operate, Platform services, web app, connectors, components, evals, infrastructure. The ordered path is in [../00-START-HERE.md](../00-START-HERE.md) and [../PLAN.md](../PLAN.md).

## Zones
- **Rigid**: ledger, tax, e-invoicing, payroll maths, audit; country packs. Deterministic, never AI-written.
- **Configurable**: custom fields, workflows, approvals, roles, print layouts, dashboards, views; composed by the AI from certified components.
- **Quarantine**: a need no component covers becomes a component request ([component-library](component-library.md)). Never a per-client fork.

## End-to-end client journey
```
Owner        Discovery        Blueprint&Library     Team        Engine       Operate
  |  chat/upload  |                  |                |            |            |
  |-------------->| interview / template draft / connectors            |            |
  |               |--draft Blueprint (provenance)-->validate           |            |
  |<--visual Blueprint, gaps, quote--|                |            |            |
  | approve (owner_approved)         |                |            |            |
  |------------------------------------->|-- review queue ---------->|            |
  |               |                  |   (HUMAN GATE: team_reviewed)  |            |
  |               |                  |<---------------|            |            |
  |               |                  |-- component requests (gaps) -> factory -> certified
  |               |                  |-- compile + plan + apply (sandbox) ------->| built_in_sandbox
  |               |                  |-- simulate a month of owner data --------->| simulated
  |<--simulation report, sign-off----|                |            |            |
  |------------------------------------------------>| cutover ----->| live      |
  |               |                  |                |            |  tool API generated per tenant
  |<=================== one chat: ask / act / report / change ===================>|
  |  "change X" ---------------------------------- Operate -> Blueprint diff -> simulate -> approve -> apply
```
States: [build-states](../../contracts/build-states.md).

## Cross-cutting rules
1. Everything is logged and traceable ([events](../../contracts/events.md)).
2. Tenants are isolated; tenant id comes from authenticated context ([tenancy-and-identity](tenancy-and-identity.md)).
3. Models are reached only through the gateway; numbers come from code ([ai-layer](ai-layer.md)).
4. Content from customer tools and documents is untrusted.
5. Arabic/RTL and i18n everywhere; themes via tokens ([theming](theming.md)); calendars and country differences via packs ([calendars-and-locale](calendars-and-locale.md), [country-packs](country-packs.md)).
6. The engine is replaceable behind the adapter ([engine-adapter](engine-adapter.md)).
7. The change engine is the apply layer of Part 2 ([change-engine](change-engine.md)).
8. Data placement and ownership: [data](data.md).

## Repo mapping
`contracts/`, `apps/engine/` (Part 3 and the change engine), `services/{discovery,blueprint,operate,gateway,control-plane}`, `web/{marketing,app}`, `connectors/`, `components/`, `evals/`, `infra/`, `agents/`.
