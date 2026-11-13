# ADR-0031: Who may write rigid-zone code, and what it must pass

Status: Proposed
Owner: partner
Approved by: pending (Eldon review; the accountant confirms the review step for tax maths before any real data)

## Context
RULES 21 and the AGENTS.md hard donts say ledger, tax, e-invoicing, payroll maths and audit are "never AI-written". Two readings exist (open question Q-18): (A) no model decides or generates these at runtime, while coding agents may write the deterministic code under controls; (B) coding agents must not write this code at all. CLAUDE.md routes "tax logic" to Opus-class models, which assumes reading A. `components/README.md` already says "rigid components never AI-written without engineer ownership", which is reading A too. Both founders build with coding agents, so reading B cannot be enforced and is not what either founder does.

PR #43 (CMP-003) shows the real risk. Its test named `test_official_sample_test_vector` claims bit-for-bit equivalence with the ZATCA sample, but its seller name and amounts differ from the example ZATCA publishes (E-invoicing Detailed Technical Guideline, section 6.4: "Bobs Basement Records", accessed 2026-11-13), so the expected value is the code's own output: the code was tested against itself. It also computes VAT itself with a hard-coded rate, making a second calculation authority next to the engine (ADR-0030 rejects that). That code subtracts a document discount from the taxable amount but not from the VAT (100.00 less 10.00 gives VAT 15.00 instead of 13.50), and sums rounded line VAT where ZATCA requires VAT rounded once at document level (Electronic Invoice XML Implementation Standard, chapter 10, accessed 2026-11-13). The risk is unverified tax maths that nobody checked, not who typed the code.

## Decision
Reading A. Coding agents may write rigid-zone code. It never merges on a model's say-so. Rigid-zone code is code under `components/compliance/`, payroll, ledger or tax paths in `apps/engine/`, and any code that computes, rounds, encodes, signs or submits a figure for a ledger, tax return, e-invoice or payroll file. It must meet four conditions:
1. **Test vectors from the source.** Every rigid-zone test that claims conformance uses a vector copied from the official source (the regulator's own document, sandbox or SDK; never a third-party library or blog, which may alter the example), with the URL and access date next to it in the test. A value produced by the code under test may be used as a regression check but is never called official or conformant.
2. **One calculation authority.** The engine, or a vetted component adopted for that job, computes amounts, tax and rounding. Our code formats, validates, encodes and transmits what that authority produced. Where we must check a figure, the check compares and fails closed; it does not substitute its own figure. Rates and rules come from the country pack (ADR-0015), never constants in code.
3. **A named human reviewer.** A founder who did not prompt the code reviews it line by line and records their name and date in the pull request. Tax and payroll maths also need the accountant's review before any real data (LEG-019).
4. **A different model reviews**, as for every change (AGENTS.md).

No model output is ever used as a figure, rate, rule or test expectation at runtime. "Certified" and "compliant" are used only after the relevant authority's sandbox or certification passes; before that, say "implemented, not yet verified".

## Alternatives rejected
- Reading B, no agent-written rigid-zone code: unenforceable, contradicts how both founders work and CLAUDE.md, and does not address the actual failure (untested maths).
- Reading A with no extra controls: the #43 self-generated "official" vector shows that a model's tests can look authoritative and prove nothing.

## Consequences
- RULES 21 and the AGENTS.md hard dont are reworded to point here once this ADR is accepted (a follow-up, not this PR).
- This ADR and Q-18 are proposed in PR #48. PR #43 is reworked to the four conditions before merge: real ZATCA vector, no own VAT computation, rate from configuration, no "certified" claim, and a named reviewer.
- The component manifest schema has no pre-review state for tax components (Q-19).
- Reviewers send back rigid-zone pull requests that lack the source of a vector or the reviewer line.

## Supersedes
None. Clarifies RULES 21 and the AGENTS.md hard dont "No AI-written ledger, tax, e-invoice or payroll logic".
