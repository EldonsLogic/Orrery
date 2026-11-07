# ADR-0010: Model strategy

Status: Accepted
Owner: eldon
Approved by: Eldon and partner

## Context
Inference cost per tenant is small compared to a price floor, but Arabic quality and reliability matter ([../strategy/06-model-strategy.md](../strategy/06-model-strategy.md)). Model prices and usage in that file are assumptions.

## Decision
All model calls go through our gateway (routing, budgets, caching, logs, regional routing, provider fallback). Use tiered models: strongest for build-time planning and hard tasks, smaller for run-time chat and extraction. Build the Arabic eval set first and refuse to ship flows below threshold. Models are hidden from customers (no picker); customers see an AI-actions budget. No self-hosting open-weight models until the triggers in strategy/06 are met.

## Alternatives rejected
- Customer picks the model: breaks evals, exposes margin.
- Self-host now: unproven Arabic quality, needs hundreds of tenants to break even.
- Customer pays tokens: scares owners.

## Consequences
- Gateway (PLT-009) and evals (QA-001 to QA-003) come before agent features.
- PDPL and region routing need counsel input (LEG-012, PLT-010).

## Supersedes
none
