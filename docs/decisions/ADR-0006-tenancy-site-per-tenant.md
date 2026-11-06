# ADR-0006: Tenancy is an isolated site per customer on shared in-country infrastructure

Status: Accepted
Owner: eldon
Approved by: Eldon; partner review pending (GOV-013)

## Context
Frappe uses one database per site. PDPL and customer trust favour strong isolation. A VPS per client kills margins and operations ([../strategy/05-hosting-and-data.md](../strategy/05-hosting-and-data.md)).

## Decision
Each customer is one isolated tenant (one engine site, own database, own file store) on shared infrastructure located in-country. No VPS per client. "One engine" means one shared codebase and component library, not one shared schema. Dedicated or hybrid hosting is a later paid option, subject to LEG-017. Tenant lifecycle: trial, active, suspended, exported, deleted.

## Alternatives rejected
- Shared schema with tenant column: weak isolation and a poor fit for Frappe.
- VPS per client: high cost, slow upgrades.

## Consequences
- Provisioning must be scripted (ERP-003, PLT-003).
- Cross-tenant tests are mandatory (SEC-004).
- Capacity planning needs the 50-tenant spike (ERP-002).
- Export and delete are per site (DAT-006, DAT-007).

## Supersedes
none
