# Session log: erp-035-invoice-document-tokens

Date: 2026-11-25
Author: partner
Tool and model: claude-code / claude-opus-5-5 (coordinator); implementation by a Claude Sonnet 5.5 child, test-first
Plan IDs: ERP-035

## Summary
The bilingual tax invoice print format (ERP-007) now takes every colour and font from the document tokens (ADR-0014) and is covered by the colour and font literal guard. This is part of the partner's Wave 2; see the 2026-11-25 partner sprint log.

## Files touched
All paths are under `apps/engine/change_engine/change_engine/`.
- `print_formats/bilingual_tax_invoice.py`:
  - The `:root` block sets `--doc-surface`, `--doc-panel`, `--doc-text`, `--doc-border`, `--brand-primary`, `--font-doc` and `--font-heading` from `document_tokens()`. Every rule uses `var()`.
  - `DEFAULT_BRANDING_PRIMARY` is now read from the primary token, lazily.
  - Muted classes use the text colour with a per-class opacity that keeps the old contrast and stays at or above WCAG 4.5:1 (lowest: `.muted` at 5.11).
  - Borders are `0.5pt solid var(--doc-border)`, where the border is the text token.
  - Titles and `.num-col` use Cairo through `--font-heading`, and `.num-col` also has `tabular-nums`.
- `print_formats/document_tokens.py`: a new `heading_font_stack`, built and validated like the body stack. A bad or missing heading token raises `DocumentTokenError`.
- `print_formats/brand_tokens_snapshot.json`: regenerated with `write_snapshot()`; it now carries the heading family.
- `print_formats/__init__.py`: `DEFAULT_BRANDING_PRIMARY` resolves lazily through the package's `__getattr__`.
- Tests:
  - `test_erp_007`: new tests for the token stacks, titles and `.num-col`, the muted-opacity contrast floor, borders without literals, and the heading token failing closed.
  - `test_erp_016`: `bilingual_tax_invoice.py` is added to the literal guard, and the snapshot test expects both families.

## Evidence
- The two target files went red (30 failures, including subtests) and then green: 198 passed, 1 skipped.
- Full change-engine suite: 1783 passed, 86 skipped, 0 failed.
- UNVERIFIED: opacity, and whether the 0.5pt hairline is rendered as 1px, in the engine's PDF renderer.

## Decisions
- The brand set has no `muted` or `border` colour. Until it does, muted text uses opacity on the text token and borders use a text-coloured hairline, with no new token invented. Whether to add proper `muted` and `border` tokens is Q-643 for Eldon (brand lane).

## Gemini 4 Argon review (at 5512122d): approve with nits; 3 Lows fixed by the coordinator
- `resolve_invoice_branding` now requires the brand primary to reach WCAG AA on both the page surface and the panel background. For example, `#757575` passes on white but fails on the panel, and is now refused.
- The muted-text test composites against both surfaces.
- "Cairo" is added to the literal guard's font names.
- The fail-closed test also checks the lazy `DEFAULT_BRANDING_PRIMARY` on both modules.
- Gemini verified that the diff is CSS-only (QR, mandatory fields and RTL layout untouched), that the snapshot matches `write_snapshot()` byte for byte, and that the lazy loading has no import-time side effects.
- Full suite: 1785 passed, 86 skipped, 0 failed.
- Q-643 asks Eldon, as the brand-lane owner, to add proper `muted` and `border` colour tokens.

## Eldon's review at f5932658 (2026-11-26): Arabic font fallback fixed
- Must fix: the font stacks had dropped `'Noto Sans Arabic', 'DejaVu Sans'`. The print loader now puts both right after the token family and before any generic family: `'Readex Pro', 'Noto Sans Arabic', 'DejaVu Sans', system-ui, sans-serif` (Cairo first for headings). The invoice keeps no font literal; the literal guard still passes. Quote, purchase order and invoice share the loader.
- New test: every document stack has both fallbacks before any generic, and the token family first. It fails before the fix; three mutants (drop either fallback, move them after the generics) are caught.
- Full suite: 1786 passed, 86 skipped. Written by Claude Sonnet 5.5 (sub-agent, no git); coordinator checked the diff.
- Q-660 asks whether the fallbacks should move into the brand tokens (brand lane).
- Gemini 4 Argon (high) re-review of the delta f5932658..2620d508: APPROVE with one Low (a token fallback that already names an Arabic font would repeat it). Fixed by the coordinator: the stack is de-duplicated case-insensitively, with a test. Full suite: 1787 passed, 86 skipped.
- Still UNVERIFIED: the real-bench PDF (greys at opacity, #F3F4F6 panels, 0.5pt borders) and whether the renderer host has either fallback font installed.

## Tokens or cost
Unknown.

## Next step
Gemini 4 Argon review, then the PR (Tier 2).
