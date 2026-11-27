# ADR-0082: Seshat for the engine, Sesh for the AI assistant

Status: Proposed
Owner: eldon
Approved by: Eldon, final founder decision of 2026-11-27 (in session); partner to confirm on this PR

## Context
Customers, investors and partners ask what powers Seshna. ADR-0016 keeps the underlying open-source core invisible, so it is never named. The product also needs a name for its AI assistant, the chat a person talks to.

## Decision
1. **Seshat** is the public name of Seshna's platform engine: the layer that turns a Blueprint into a running business system, including compilation, components, country packs, the approval floor and the engine adapter. Seshat is what we name when asked "what runs Seshna?".
2. **Sesh** is the name of the AI assistant, in the product (for example "Ask Sesh") and in marketing.
3. Both names follow the Seshna rules (ADR-0066). They are written in Latin letters only, never in Arabic script and never translated. In Arabic text they sit inside `<bdi>`.
4. **The underlying open-source core stays unnamed** in anything customer-facing (ADR-0016 is unchanged). Seshat is our layer and our name, not a rename of the core. Whether the core may be named to investors under NDA during due diligence stays a founders' question.
5. Both names join the LEG-008 trademark search (classes 9, 35 and 42) in Saudi Arabia, the UAE, Egypt and Qatar. Until it clears, they are used in product and marketing copy, without a registered mark symbol.

## Alternatives rejected
- No engine name: leaves "what runs it?" unanswered and invites guesses about the core.
- Naming the core: forbidden by ADR-0016.

## Consequences
- brand.json lists both names (BRD-015).
- Product and marketing copy name the assistant Sesh. The i18n catalogues pick this up under the screen rows.
- The trademark search covers three names: Seshna, Seshat and Sesh.

## Supersedes
None.
