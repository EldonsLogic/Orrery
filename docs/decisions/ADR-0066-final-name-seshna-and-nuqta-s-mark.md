# ADR-0066: Final product name Seshna and the Nuqta S mark

Status: Accepted
Owner: eldon
Approved by: both founders, decided 2026-11-23; recorded by Eldon for both (GOV-069 PR and log)

## Context
ADR-0001 made "Orrery" a working codename and told every new text to say "the platform" until a final name was cleared (LEG-008) and the identity decided (BRD-003). ADR-0011 made brand guidelines v1 (the Quadrant mark, Alexandria headings, Readex Pro body) the interim design system and treated the logo as a placeholder. On 2026-11-23 the founders chose the final name, the mark and the type system from a logo exploration kit (Nuqta S, draft v3, marked "Not cleared for trademark"). The kit lives outside the repo; BRD-009 brings its assets into `docs/brand/`.

Counsel's trademark clearance (LEG-008) has not happened, and the domain is not yet registered (LEG-005). The founders chose to decide and publish anyway.

## Decision
1. **Name and domain.** The product's final name is **Seshna**, on the domain **seshna.com**. The founders intend it not to change.
2. **Latin only.** The name is always written in Latin letters, "Seshna" with a capital S, in every language, layout and channel. It is never written in Arabic script and never translated. In Arabic text the Latin name is isolated as left-to-right (wrap it in `<bdi>` in HTML). There is no Arabic wordmark or lockup; the Latin lockup is used unchanged in right-to-left layouts. This answers Q-4.
3. **The mark is Nuqta S**: the scribe's rhombic dot cut along the reed pen's angle, its two halves ending in round strokes so the pair reads as an S. It is never mirrored, flipped or rotated, including in right-to-left layouts. It replaces the Quadrant mark of brand guidelines v1.
4. **The wordmark** is Cairo Bold (700), outlined to paths, never retyped in a font.
5. **Typefaces.** Cairo replaces Alexandria for headings. Readex Pro stays for body and interface text. The system stays at two families.
6. **Palette unchanged.** The brand guidelines v1 colours stay (Cobalt, Coral, Carbon, Chalk and the rest). Coral is never used on the wordmark. Colours and fonts still come only from tokens (ADR-0014).
7. **Repo and GitHub organisation.** The repo stays `EldonsLogic/Orrery` for now. Renaming the repo and organisation, and internal identifiers such as package names or environment variables, happens under GOV-002, not here.
8. **Rule 52 waived for this name.** Eldon knowingly chose, for both founders, to make the name public before seshna.com and the handles are registered. RULES 52 still applies to any other candidate name.

## Alternatives rejected
- Keep the working name and "the platform" until clearance: leaves product, website and brand work blocked on an open-ended legal step, and the team already uses the new name.
- Wait for counsel's clearance before deciding: same blockage; the founders accept the risk of a forced change instead.
- Cairo for the wordmark only, keeping Alexandria for headings: adds a third type family to load, license and keep consistent.

## Consequences
- **Trademark not cleared.** LEG-008 stays open. Counsel may advise that Seshna or the Nuqta S mark cannot be registered or used in one of the four markets, and could force a change despite the founders' intent. Q-602 asks counsel the registrability question; R-034 tracks the risk. Until counsel answers, brand material says "Not cleared for trademark" where the kit does.
- **Domain not yet registered.** LEG-005 now means registering seshna.com and the @seshna handles. Publishing the name first exposes it to squatting; the founders accept that risk.
- **Engine invisibility unchanged.** ADR-0016 still applies: nothing a customer sees says "Frappe" or "ERPNext", and neither may appear in the product name, domain or ads (LEG-009).
- **Work this unlocks.** BRD-003 is done. BRD-009 regenerates every logo file, size, favicon and social size and the guidelines from the Nuqta S kit, with Cairo headings. WEB-028 self-hosts Cairo and Readex Pro instead of Alexandria. Font licences (Cairo, SIL OFL 1.1) are recorded under BRD-011.
- New text uses "Seshna" for the product or "the platform" where a generic term reads better.

## Supersedes
- ADR-0001: the working-name rule ("say 'the platform' in new text") and the wait for clearance before naming the product. Its rule against "ERPNext" or "Frappe" in a product name stays.
- ADR-0011, in part: the placeholder logo and the Quadrant mark, and Alexandria as the heading and wordmark typeface in brand guidelines v1. The palette and the rest of the interim design system stay.
