# ADR-0016: The engine is invisible to customers

Status: Accepted
Owner: eldon
Approved by: Eldon and partner

## Context
The platform runs on an open-source engine (ADR-0002). Customers buy Orrery, not the engine. Showing the engine's name or its default screens weakens the product, confuses support, invites comparison with a different product, and conflicts with the engine's trademark policy on product naming and advertising.

## Decision
No customer-visible surface says "Frappe" or "ERPNext", in the front end or the back end. Customer-visible means anything a tenant user, their customers or an outside observer can see or measure:
- UI text, page titles, favicons, login and password-reset pages, error and validation messages, notifications, emails, PDFs and print formats.
- API paths, field names, error shapes, response headers, cookie names, URLs, static asset paths, client-side bundles and globals, robots and sitemap files, hostnames.
- Public documentation, help centre, status page, store listings, marketing.

How:
- The engine runs headless on an internal network and is never reachable directly from the internet. Its Desk and default web routes are disabled for tenants.
- All traffic goes through our gateway and our own web app. The gateway exposes our own API paths, rewrites or blocks engine paths, strips engine-identifying headers, renames cookies, and maps engine errors to our own error model and language.
- Print formats, email templates and PDFs are ours, built from tokens (ADR-0014); no engine default templates reach customers.
- The product UI never ships engine client libraries or exposes engine globals.

Allowed (internal only): code identifiers, package and app names, imports, configuration, infrastructure, ADRs and internal docs, the team's own tooling, `NOTICE.md`. A legally required open-source notices page is allowed only if counsel confirms it is required (LEG item); it would be the single customer-visible exception.

Customers' own references to other products (for example importing from Odoo or another ERP) are outside this rule.

## Enforcement
- `scripts/check_repo_hygiene.py` fails if the engine's name appears in `web/`, `docs/brand/`, or in locale, template, fixture, print-format or public-asset folders (outside the engine apps).
- A staging crawl test (plan item) fetches pages, API responses, headers, cookies and bundles and fails on any engine marker.
- Reviewers and agents treat any engine marker on a customer path as a defect.

## Alternatives rejected
- Showing "powered by" the engine: no customer value, trademark risk.
- Re-skinning the engine's Desk: still exposes its paths, headers and behaviours, and ties us to its UI.

## Consequences
- The product UI, gateway and error mapping are required work, not polish (see plan rows tied to this ADR).
- Engine upgrades must not change customer-visible behaviour; the gateway contract is ours.
- Supports replaceability of the engine (ADR-0002, adapter).

## Supersedes
none
