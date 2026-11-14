# ADR-0031: Who may write rigid-zone code, and what it must pass

Status: Accepted
Owner: partner
Approved by: both founders. Eldon's answer to Q-18, "reading A" under these four conditions, was posted on PR #48 on 2026-11-14 at his instruction. The partner accepted it when asking for it to be recorded (log `2026-11-14-partner-claude-code-gov-040-founder-answers.md`).

## Context
RULES 21 and the AGENTS.md hard donts say ledger, tax, e-invoicing, payroll maths and audit are "never AI-written". Two readings exist (open question Q-18): (A) no model decides or generates these at runtime, while coding agents may write the deterministic code under controls; (B) coding agents must not write this code at all. CLAUDE.md routes "tax logic" to Opus-class models, which assumes reading A. `components/README.md` already says "rigid components never AI-written without engineer ownership", which is reading A too. Both founders build with coding agents, so reading B cannot be enforced and is not what either founder does.

PR #43 (CMP-003), as first written, showed the real risk. This paragraph is history: #43 was reworked afterwards (commit be175aa) to remove its own VAT computation and use the real ZATCA vector. Its test named `test_official_sample_test_vector` claims bit-for-bit equivalence with the ZATCA sample, but its seller name and amounts differ from the example ZATCA publishes (E-invoicing Detailed Technical Guideline, section 6.4: "Bobs Basement Records", accessed 2026-11-13), so the expected value is the code's own output: the code was tested against itself. It also computes VAT itself with a hard-coded rate, making a second calculation authority next to the engine (the proposed ADR-0030 argues against that; it is still Proposed). That code subtracts a document discount from the taxable amount but not from the VAT (100.00 less 10.00 gives VAT 15.00 instead of 13.50), and sums rounded line VAT where ZATCA requires VAT rounded once at document level (Electronic Invoice XML Implementation Standard, chapter 10, accessed 2026-11-13). The risk is unverified tax maths that nobody checked, not who typed the code.

## Decision
Reading A. Coding agents may write rigid-zone code. It never merges on a model's say-so. Rigid-zone code is code under `components/compliance/`, payroll, ledger or tax paths in `apps/engine/`, and any code that computes, rounds, encodes, signs or submits a figure for a ledger, tax return, e-invoice or payroll file. It must meet the four conditions the founders set:
1. **Tested against official vectors.** Every rigid-zone test that claims conformance uses a vector copied from the official source: the regulator's own document, sandbox or SDK. Never use a third-party library or blog, which may alter the example. The URL and access date sit next to the vector in the test. A value produced by the code under test may serve as a regression check, but it is never called official or conformant.
2. **Line-by-line human review.** A founder who did not prompt the code reviews it line by line and records their name and the date in the pull request.
3. **Accountant review of tax maths before Phase 2.** Tax and payroll maths need a qualified accountant's review before Phase 2, and in any case before real data (LEG-019).
4. **A logged model and prompt.** The session log names the model that wrote the code and keeps the prompt or brief it was given, so the review can see what was asked.

These also apply, as they do to every change:
- **A different model reviews it** (AGENTS.md).
- **One calculation authority.** The engine, or a vetted component adopted for that job, computes amounts, tax and rounding. Our code formats, validates, encodes and transmits what that authority produced. Where we must check a figure, the check compares and fails closed; it never substitutes its own figure. Rates and rules come from the country pack (ADR-0015), never from constants in code.

No model output is ever used as a figure, rate, rule or test expectation at runtime. "Certified" and "compliant" are used only after the relevant authority's sandbox or certification passes; before that, say "implemented, not yet verified".

## Alternatives rejected
- Reading B, no agent-written rigid-zone code: unenforceable, contradicts how both founders work and CLAUDE.md, and does not address the actual failure (untested maths).
- Reading A with no extra controls: the #43 self-generated "official" vector shows that a model's tests can look authoritative and prove nothing.

## Consequences
- Follow-ups, not part of this PR:
  - Reword RULES 21 and the AGENTS.md hard dont to point here.
  - Reword the `rigid` description in `contracts/component.manifest.schema.json` (line 20: "deterministic, never AI-written") to match. That file is in the contracts lane (Eldon).
- PR #43 must meet the four conditions before it merges:
  - The real ZATCA vector. Done in be175aa.
  - A named line-by-line reviewer.
  - Accountant review before Phase 2.
  - A logged model and prompt.
- The one-authority rule also applies to #43: it does not compute its own VAT, it takes the rate from configuration, and it makes no "certified" claim.
- The component manifest schema has no pre-review state for tax components. The founders answered Q-19: add a pre-review level, or require at least one named reviewer login. That needs a contracts-lane ADR (Eldon).
- Reviewers send back rigid-zone pull requests that lack the source of a vector or the reviewer line.

## Supersedes
None. Clarifies RULES 21 and the AGENTS.md hard dont "No AI-written ledger, tax, e-invoice or payroll logic".
