# ADR-0004: One chat, anyone chats, role-based views

Status: Accepted
Owner: eldon
Approved by: Eldon; partner review pending (GOV-013)

## Context
Early idea was a builder UI plus a separate operator UI. Owners and staff both need the same assistant, and permissions must not be bypassed by chat.

## Decision
There is one chat with modes (discover, ask, act, change), not two UIs. Anyone in the company can chat. Each person gets their own view (screens and tools generated from role, function and scope). The chat acts with the calling user's own permissions; it has no privileges of its own. Change requests go through the Blueprint path (preview, approve, apply, audit).

## Alternatives rejected
- Separate builder and operator UIs: duplicate effort, inconsistent permissions.
- Owner-only chat: wastes the staff-level value.

## Consequences
- Tool API calls are checked against the caller's role and scope (OPR-004).
- View generation depends on role mapping (ERP-008, OPR-011).
- Prompt-injection defence matters because every user can talk to a tool-using agent (SEC-003).

## Supersedes
none
