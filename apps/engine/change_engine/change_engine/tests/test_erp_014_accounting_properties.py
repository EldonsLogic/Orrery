"""ERP-014: accounting correctness property tests (ledger balance, VAT, rounding, reversal, stock tie-out).

Two layers, both stdlib only (seeded ``random`` instead of a property-testing library, so no new dependency):

* Pure tests (always run, CI): the invariant checkers and the decimal oracle used below, checked on
  seeded synthetic data and on the bench evidence recorded in ADR-0033.
* Live tests (skip unless a bench is named): seeded synthetic invoices, credit notes, cancellations and
  stock moves are posted on a throwaway site by ``erp_014_bench_probe.py``; every check reads the
  engine's stored amounts as decimal strings. The engine computes every figure; this file only checks.

Run the live layer against your own bench (never someone else's Compose project)::

    ERP014_COMPOSE_PROJECT=<your project> ERP014_SITE=<synthetic site> \
    PYTHONPATH=apps/engine/change_engine python3 -m unittest \
    apps/engine/change_engine/change_engine/tests/test_erp_014_accounting_properties.py -v

``REQUIRE_ERP014_LIVE=1`` (set by real-bench CI, ERP-031) turns the skip into a failure when no bench is named.

More examples: ``ERP014_EXAMPLES=200`` (default 6 invoices per company; pure tests use 25x that) and a
different ``ERP014_SEED``. The site must be disposable: the probe creates two synthetic companies on it.

Rates (checked only as the configured template rate; the engine, not this file, applies them). Sources are
the official PDFs, fetched and read 2026-11-20 (YYYY-MM-DD):
* KSA standard VAT 15%: ZATCA, Guideline on Imports and Exports under VAT Provision (states 15% on taxable
  supplies and imports), https://zatca.gov.sa/en/HelpCenter/guidelines/Documents/Guideline-on-Imports-and-Exports-under-VAT-Provision.pdf
  The 2020-07-01 start date is not stated in that document: UNVERIFIED here (see country-matrix K5).
* UAE standard VAT 5%: Federal Decree-Law No. 8 of 2017 and amendments, Art. 3 (Tax Rate), "a standard rate of 5%",
  https://tax.gov.ae/DataFolder/Files/Legislation/Federal%20Decree-Law%20No.%208%20of%202017%20and%20amendments%20-%20For%20Publishing.pdf
  (see country-matrix U5). The earlier FAQ page link was dropped: it is not a primary source for the rate.
Rounding rule (round once per tax row, half away from zero) is the engine's configured behaviour from ADR-0033,
not a statutory finding. ZATCA's XML Implementation Standard v1.2 (document level, half-up to 2 decimals) is
consistent for positive amounts; UAE per-row rounding and the negative-amount tie-break are UNVERIFIED pending
an accountant (Cabinet Decision No. 52 of 2017 Art. 61 only says "mathematical rounding" to the nearest fils).
Zero-rated and exempt lines both carry a 0% rate on the line; their legal difference (input-tax recovery,
reporting box) is not a ledger-arithmetic property and is not tested here.
"""
from __future__ import annotations

import ast
import json
import os
import random
import subprocess
import unittest
from collections import Counter, defaultdict
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[5]
COMPOSE_FILE = REPO_ROOT / "infra" / "dev" / "docker" / "docker-compose.dev.yml"
PROBE_FILE = Path(__file__).with_name("erp_014_bench_probe.py")
PROBE = "apps/change_engine/change_engine/tests/erp_014_bench_probe.py"
CENT = Decimal("0.01")
VAT_RATES = {"ERP14 Trading KSA": 15, "ERP14 Trading UAE": 5}
SEED = int(os.environ.get("ERP014_SEED", "14014"))
EXAMPLES = int(os.environ.get("ERP014_EXAMPLES", "6"))
LIVE_ENV = ("ERP014_COMPOSE_PROJECT", "ERP014_SITE", "REQUIRE_ERP014_LIVE")


def live_skip_reason(env, project_var: str, site_var: str, require_var: str):
    """Why a live layer skips, or None when it must run. ERP-031: a REQUIRE flag of 1 never skips (the class
    then fails in ``live_config_problem`` if no bench is named); also used by the ERP-015 live layer."""
    if env.get(require_var) == "1" or (env.get(project_var) and env.get(site_var)):
        return None
    return (f"No bench configured: set {project_var} and {site_var} to a disposable synthetic site on your own "
            "Compose project (see module docstring)")


def live_config_problem(env, project_var: str, site_var: str, require_var: str):
    """The fail-closed rule: one bench variable alone, or the REQUIRE flag without a bench, is an error."""
    project, site = env.get(project_var), env.get(site_var)
    if bool(project) != bool(site):
        return f"set both {project_var} and {site_var}, or neither"
    if env.get(require_var) == "1" and not (project and site):
        return f"{require_var}=1 but no bench is configured"
    return None


# ---- decimal oracle and invariant checkers (test code: they check, they never post) ----

def half_away(x: Decimal, places: int = 2) -> Decimal:
    """ADR-0033 Commercial Rounding. Python's ROUND_HALF_UP rounds half away from zero for negatives too."""
    return x.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def expected_row_tax(net_amounts, rates) -> Decimal:
    """Engine rule with ``round_row_wise_tax = 0`` (erpnext/controllers/taxes_and_totals.py, calculate_taxes
    and round_off_totals): per-line tax = line net x rate / 100 left unrounded, summed over lines, rounded once."""
    return half_away(sum((Decimal(n) * Decimal(r) / 100 for n, r in zip(net_amounts, rates)), Decimal(0)))


def unbalanced_vouchers(gl_rows):
    """(company, voucher type, voucher no) whose debits and credits differ, in company currency."""
    sums = defaultdict(lambda: [Decimal(0), Decimal(0)])
    for r in gl_rows:
        key = (r["company"], r["voucher_type"], r["voucher_no"])
        sums[key][0] += Decimal(r["debit"])
        sums[key][1] += Decimal(r["credit"])
    return {k: (d, c) for k, (d, c) in sums.items() if d != c}


def mirror_mismatch(gl_rows) -> Counter:
    """Rows not matched by an exact negation (same account, debit and credit swapped). Empty means every
    posting is exactly reversed: cancel under the immutable ledger, or an invoice plus its full credit note."""
    fwd = Counter((r["account"], Decimal(r["debit"]), Decimal(r["credit"])) for r in gl_rows)
    rev = Counter((r["account"], Decimal(r["credit"]), Decimal(r["debit"])) for r in gl_rows)
    return (fwd - rev) + (rev - fwd)


def off_cent(values):
    """Amounts that are not whole cents (float drift or unrounded storage)."""
    return [v for v in values if Decimal(v) != half_away(Decimal(v))]


OPENING_RECEIPT = {"type": "Material Receipt", "qty": "100", "rate": "10.00"}
# Forced after the golden issue: a receipt at a NEW rate, an issue, another receipt and another issue. Moving Average
# and FIFO give different values from the first of these issues on, whatever EXAMPLES and the seed are.
FORCED_STOCK = [{"type": "Material Receipt", "qty": "40", "rate": "20.00"}, {"type": "Material Issue", "qty": "30"},
                {"type": "Material Receipt", "qty": "20", "rate": "5.00"}, {"type": "Material Issue", "qty": "10"}]


def expected_stock_steps(moves, method="Moving Average"):
    """(qty, value) after each move, from the opening receipt, in exact Decimal. Moving Average values an issue at
    stock value / qty on hand; FIFO consumes the oldest layers first."""
    qty, value, layers, out = Decimal(0), Decimal(0), [], []
    for mv in [OPENING_RECEIPT] + list(moves):
        q = Decimal(mv["qty"])
        if mv["type"] == "Material Receipt":
            r = Decimal(mv["rate"])
            qty, value = qty + q, value + q * r
            layers.append([q, r])
        elif method == "Moving Average":
            value, qty = value - value * q / qty, qty - q
        else:
            left, qty = q, qty - q
            while left:
                take = min(left, layers[0][0])
                value, left, layers[0][0] = value - take * layers[0][1], left - take, layers[0][0] - take
                if not layers[0][0]:
                    layers.pop(0)
        out.append((qty, value))
    return out


def gross(lines) -> Decimal:
    return sum((half_away(Decimal(ln["qty"]) * Decimal(ln["rate"])) for ln in lines), Decimal(0))


def make_inputs(seed: int, n: int) -> dict:
    """Seeded synthetic probe input: invoices with mixed standard / zero-rated / exempt lines, rates chosen
    to land on half-cent tax values, stock moves that never exceed stock on hand, rounding samples.
    Forced cases are always present, whatever ``n``: a .005 boundary across several lines (row-wise and
    line-wise rounding differ), Z-only and E-only invoices, a document discount, and the stock sequence above."""
    rnd = random.Random(seed)
    cases = []
    for company in VAT_RATES:
        for i in range(n):
            k = rnd.randint(1, 5)
            lines = [{"category": rnd.choice("SSSZE"), "qty": str(rnd.randint(1, 12)),
                      "rate": f"{rnd.randint(1, 99999) / 100:.2f}"} for _ in range(k)]
            if not any(ln["category"] == "S" for ln in lines):
                lines[0]["category"] = "S"
            if i == 0:  # a known half-cent case: 0.70 x 15% = 0.105 and 2.10 x 5% = 0.105 (ADR-0033)
                lines = [{"category": "S", "qty": "1", "rate": "0.70" if VAT_RATES[company] == 15 else "2.10"}]
            perm = list(range(len(lines)))
            rnd.shuffle(perm)
            action = ["keep", "cancel", "return"][i % 3]
            cases.append({"case_id": f"{company[-3:]}-{i}", "company": company, "lines": lines,
                          "permutation": perm, "action": action})
        half = "0.70" if VAT_RATES[company] == 15 else "2.10"  # x rate = 0.105 on every standard line
        forced = {
            "boundary": ([{"category": c, "qty": "1", "rate": half} for c in "SSSZE"], 0, "keep"),  # row 0.32, per line 0.33
            "zero-only": ([{"category": "Z", "qty": "3", "rate": "19.99"}, {"category": "Z", "qty": "1", "rate": "0.05"}], 0, "keep"),
            "exempt-only": ([{"category": "E", "qty": "2", "rate": "45.50"}, {"category": "E", "qty": "7", "rate": "3.33"}], 0, "keep"),
            "discount": ([{"category": "S", "qty": "3", "rate": "33.33"}, {"category": "S", "qty": "2", "rate": half},
                          {"category": "Z", "qty": "1", "rate": "12.34"}], 10, "keep"),
        }
        for name, (lines, discount, action) in forced.items():
            perm = list(reversed(range(len(lines))))
            cases.append({"case_id": f"{company[-3:]}-{name}", "company": company, "lines": lines,
                          "permutation": perm, "action": action, "discount_percent": discount})
    on_hand, moves = 100, [{"type": "Material Issue", "qty": "10"}] + [dict(m) for m in FORCED_STOCK]
    on_hand += -10 + 40 - 30 + 20 - 10  # golden path: 10 of 100 leave at cost, then the forced sequence
    for _ in range(n):
        if rnd.random() < 0.5:
            q = rnd.randint(1, 30)
            moves.append({"type": "Material Receipt", "qty": str(q), "rate": f"{rnd.randint(500, 2500) / 100:.2f}"})
            on_hand += q
        else:
            q = rnd.randint(1, max(1, on_hand // 2))
            moves.append({"type": "Material Issue", "qty": str(q)})
            on_hand -= q
    samples = [f"{rnd.choice('-+')}{rnd.randint(0, 999)}.{rnd.randint(0, 99):02d}5" for _ in range(4 * n)]
    samples += ["0.105", "-0.105", "1.005", "-1.005", "2.675", "-2.675", "0.125", "-0.125", "2.5", "-2.5"]
    return {"cases": cases, "stock_moves": moves, "rounding_samples": samples}


# ---- pure layer ----

class TestOracleAndCheckers(unittest.TestCase):
    def test_oracle_matches_adr_0033_bench_evidence(self):
        for raw, want in [("2.5", "3"), ("-2.5", "-3"), ("0.125", "0.13"), ("-0.125", "-0.13"), ("1.005", "1.01"),
                          ("-1.005", "-1.01"), ("2.675", "2.68"), ("-2.675", "-2.68"), ("-0.105", "-0.11")]:
            places = 0 if "." in raw and len(raw.split(".")[1]) == 1 else 2
            self.assertEqual(half_away(Decimal(raw), places), Decimal(want), raw)
        self.assertEqual(expected_row_tax(["0.70"], [15]), Decimal("0.11"))  # ADR-0033: 0.70 at 15% -> 0.11

    def test_rounding_is_symmetric_and_order_invariant(self):
        rnd = random.Random(SEED)
        for _ in range(25 * EXAMPLES):
            x = Decimal(rnd.randint(-10**7, 10**7)) / 1000
            self.assertEqual(half_away(-x), -half_away(x))
            nets = [Decimal(rnd.randint(1, 10**6)) / 100 for _ in range(rnd.randint(1, 8))]
            rates = [rnd.choice([15, 5, 0]) for _ in nets]
            pairs = list(zip(nets, rates))
            rnd.shuffle(pairs)
            self.assertEqual(expected_row_tax(nets, rates), expected_row_tax(*zip(*pairs)))

    def test_round_once_stays_within_half_cent_per_line_of_rounding_each_line(self):
        rnd = random.Random(SEED + 1)
        for _ in range(25 * EXAMPLES):
            nets = [Decimal(rnd.randint(1, 10**6)) / 100 for _ in range(rnd.randint(1, 8))]
            rates = [rnd.choice([15, 5, 0, 0]) for _ in nets]
            per_line = sum(half_away(n * r / 100) for n, r in zip(nets, rates))
            self.assertLessEqual(abs(expected_row_tax(nets, rates) - per_line), Decimal("0.005") * len(nets))
            self.assertEqual(expected_row_tax(nets, rates),
                             expected_row_tax([n for n, r in zip(nets, rates) if r], [r for r in rates if r]))

    def test_checkers_catch_a_one_cent_defect(self):
        rnd = random.Random(SEED + 2)
        for _ in range(25 * EXAMPLES):
            amt = [Decimal(rnd.randint(1, 10**6)) / 100 for _ in range(rnd.randint(1, 4))]
            rows = [{"company": "C", "voucher_type": "Sales Invoice", "voucher_no": "V", "account": f"A{i}",
                     "debit": str(a), "credit": "0"} for i, a in enumerate(amt)]
            rows.append({"company": "C", "voucher_type": "Sales Invoice", "voucher_no": "V", "account": "S",
                         "debit": "0", "credit": str(sum(amt))})
            self.assertEqual(unbalanced_vouchers(rows), {})
            reversal = [{**r, "debit": r["credit"], "credit": r["debit"]} for r in rows]
            self.assertFalse(mirror_mismatch(rows + reversal))
            reversal[0]["credit"] = str(Decimal(reversal[0]["credit"]) + CENT)
            self.assertTrue(mirror_mismatch(rows + reversal))
            self.assertTrue(unbalanced_vouchers(rows + reversal))
        self.assertEqual(off_cent(["1.10", "2.000000000", "0.105"]), ["0.105"])

    def test_inputs_are_deterministic_and_bounded(self):
        a, b = make_inputs(SEED, EXAMPLES), make_inputs(SEED, EXAMPLES)
        self.assertEqual(a, b)
        on_hand = 100
        for mv in a["stock_moves"]:
            on_hand += int(mv["qty"]) * (1 if mv["type"] == "Material Receipt" else -1)
            self.assertGreaterEqual(on_hand, 0)
        for case in a["cases"]:
            self.assertTrue(case["lines"])
            self.assertEqual(sorted(case["permutation"]), list(range(len(case["lines"]))))

    def test_forced_cases_exist_for_any_example_count(self):
        for n in (1, EXAMPLES):
            cases = {c["case_id"]: c for c in make_inputs(SEED, n)["cases"]}
            for company in VAT_RATES:
                tag = company[-3:]
                boundary = cases[f"{tag}-boundary"]
                nets = [half_away(Decimal(ln["qty"]) * Decimal(ln["rate"])) for ln in boundary["lines"]]
                rates = [VAT_RATES[company] if ln["category"] == "S" else 0 for ln in boundary["lines"]]
                per_line = sum(half_away(n_ * r / 100) for n_, r in zip(nets, rates))
                self.assertNotEqual(expected_row_tax(nets, rates), per_line, "row-wise and line-wise must differ")
                self.assertEqual({ln["category"] for ln in boundary["lines"]}, set("SZE"))
                self.assertEqual({ln["category"] for ln in cases[f"{tag}-zero-only"]["lines"]}, {"Z"})
                self.assertEqual({ln["category"] for ln in cases[f"{tag}-exempt-only"]["lines"]}, {"E"})
                self.assertGreater(cases[f"{tag}-discount"]["discount_percent"], 0)

    def test_forced_stock_sequence_separates_moving_average_from_fifo(self):
        for n in (1, EXAMPLES):
            moves = make_inputs(SEED, n)["stock_moves"]
            self.assertEqual(moves[1:1 + len(FORCED_STOCK)], FORCED_STOCK)
            ma, fifo = expected_stock_steps(moves), expected_stock_steps(moves, "FIFO")
            self.assertEqual(len(ma), 1 + len(moves))
            self.assertEqual([q for q, _ in ma], [q for q, _ in fifo])
            self.assertEqual(ma[:2], fifo[:2])  # opening and golden issue: identical (why FIFO was not caught)
            self.assertGreater(abs(ma[3][1] - fifo[3][1]), 50, "first issue after the new-rate receipt")
            self.assertTrue(all(q > 0 for q, _ in ma))
        self.assertEqual(expected_stock_steps([{"type": "Material Issue", "qty": "10"}])[1],
                         (Decimal(90), Decimal("900.00")))

    def test_live_bench_env_is_all_or_nothing(self):
        """Fail closed: one variable alone (or REQUIRE_ERP014_LIVE=1 without a bench) must not skip silently."""
        self.assertIsNone(live_config_problem(os.environ, *LIVE_ENV))

    def test_probe_is_valid_python_with_the_expected_shape(self):
        """The probe only runs inside a bench, so CI would never notice it rotting: parse it here."""
        tree = ast.parse(PROBE_FILE.read_text(encoding="utf-8"), filename=str(PROBE_FILE))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                imported.add((node.module or "").split(".")[0])
        self.assertLessEqual(imported, {"__future__", "json", "os", "sys", "change_engine", "erpnext", "frappe"})
        self.assertFalse([n for n in ast.walk(tree) if isinstance(n, ast.Assert)], "the probe never asserts")
        self.assertIn("main", {n.name for n in tree.body if isinstance(n, ast.FunctionDef)})
        self.assertEqual(self._probe_float_str_amounts(tree), [], "read amounts with CAST(... AS CHAR), not str(float)")

    @staticmethod
    def _probe_float_str_amounts(tree):
        bad = []
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "str"
                    and node.args and isinstance(node.args[0], ast.Attribute)
                    and node.args[0].attr in {"net_amount", "net_total", "grand_total", "total_taxes_and_charges"}):
                bad.append(ast.unparse(node))
        return bad


# ---- live layer ----

@unittest.skipIf(live_skip_reason(os.environ, *LIVE_ENV) is not None, live_skip_reason(os.environ, *LIVE_ENV) or "")
class TestLiveEngineProperties(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        problem = live_config_problem(os.environ, *LIVE_ENV)
        if problem:  # REQUIRE_ERP014_LIVE=1 without a bench: a failure, never a skip (ERP-031)
            raise AssertionError(problem)
        cls.inputs = make_inputs(SEED, EXAMPLES)
        payload = json.dumps({"site": os.environ["ERP014_SITE"], **cls.inputs})
        res = subprocess.run(
            ["docker", "compose", "--project-name", os.environ["ERP014_COMPOSE_PROJECT"], "--env-file", os.devnull,
             "-f", str(COMPOSE_FILE), "exec", "-T", "engine", "env/bin/python", PROBE],
            input=payload, capture_output=True, text=True, timeout=1800, check=False,
            env={**os.environ, "DB_ROOT_PASSWORD": "unused", "ADMIN_PASSWORD": "unused"})
        if res.returncode != 0:
            raise RuntimeError(f"probe failed rc={res.returncode}:\n{res.stderr[-4000:]}")
        out = res.stdout
        cls.data = json.loads(out[out.index('{"settings"'):])

    def test_provisioning_settings_are_the_adr_0033_ones(self):
        s = self.data["settings"]
        self.assertEqual(s["rounding_method"], "Commercial Rounding")
        self.assertEqual(s["valuation_method"], "Moving Average")
        self.assertEqual(int(s["enable_immutable_ledger"]), 1)
        self.assertEqual(int(s["round_row_wise_tax"] or 0), 0, "oracle assumes tax rounded once per row")
        self.assertEqual(s["company_currency"], {"ERP14 Trading KSA": "SAR", "ERP14 Trading UAE": "AED"})

    def test_1_every_voucher_balances_in_company_currency(self):
        self.assertGreater(len(self.data["gl"]), 0)
        self.assertEqual(unbalanced_vouchers(self.data["gl"]), {})

    def test_2_invoice_tax_follows_the_documented_rule(self):
        cases = {c["case_id"]: c for c in self.inputs["cases"]}
        for inv in self.data["invoices"]:
            with self.subTest(inv["case_id"]):
                case = cases[inv["case_id"]]
                self.assertEqual(len(inv["lines"]), len(case["lines"]))
                if case.get("discount_percent"):  # engine distributes the document discount; bound it, do not mirror it
                    expected_net = half_away(gross(case["lines"]) * (1 - Decimal(case["discount_percent"]) / 100))
                    self.assertLessEqual(abs(Decimal(inv["totals"]["net_total"]) - expected_net), CENT * len(case["lines"]))
                else:  # never trust the engine's own line amount: recompute it from the seeded input
                    for ln, src in zip(inv["lines"], case["lines"]):
                        self.assertEqual(Decimal(ln["net_amount"]), half_away(Decimal(src["qty"]) * Decimal(src["rate"])))
                nets = [ln["net_amount"] for ln in inv["lines"]]
                rates = [inv["vat"] if ln["category"] == "S" else 0 for ln in inv["lines"]]
                self.assertEqual(inv["vat"], VAT_RATES[inv["company"]])
                tax = Decimal(inv["tax_amount"])
                self.assertEqual(tax, expected_row_tax(nets, rates))
                per_line = sum(half_away(Decimal(n) * r / 100) for n, r in zip(nets, rates))
                self.assertLessEqual(abs(tax - per_line), Decimal("0.005") * len(nets))
                t = inv["totals"]
                self.assertEqual(Decimal(t["taxes"]), tax)
                self.assertEqual(Decimal(t["net_total"]), sum(Decimal(n) for n in nets))
                self.assertEqual(Decimal(t["grand_total"]), Decimal(t["net_total"]) + tax)

    def test_3_totals_invariant_under_line_order_and_whole_cents(self):
        for inv in self.data["invoices"]:
            with self.subTest(inv["case_id"]):
                for key in ("net_total", "taxes", "grand_total"):
                    self.assertEqual(Decimal(inv["permuted"][key]), Decimal(inv["totals"][key]), key)
        amounts = [r[k] for r in self.data["gl"] for k in ("debit", "credit")]
        amounts += [v for inv in self.data["invoices"] for v in inv["totals"].values()]
        self.assertEqual(off_cent(amounts), [])

    def test_3_engine_rounding_is_half_away_from_zero(self):
        wrong = [(r["value"], r["engine"]) for r in self.data["rounding"]
                 if Decimal(r["engine"]) != half_away(Decimal(r["value"]))]
        self.assertEqual(wrong, [])

    def test_4_cancel_and_credit_note_exactly_negate(self):
        by_voucher = defaultdict(list)
        for r in self.data["gl"]:
            by_voucher[r["voucher_no"]].append(r)

        def has_amount(rows):  # catches "zeroed in place" instead of a reversing entry under the immutable ledger
            return any(Decimal(r["debit"]) != 0 or Decimal(r["credit"]) != 0 for r in rows)

        for inv in self.data["invoices"]:
            with self.subTest(inv["case_id"], action=inv["action"]):
                rows = by_voucher[inv["voucher_no"]]
                if inv["action"] == "cancel":
                    self.assertTrue(rows, "a cancelled invoice must still show its postings and their reversal")
                    self.assertTrue(has_amount(rows))
                    self.assertFalse(mirror_mismatch(rows))
                elif inv["action"] == "return":
                    ret_rows = by_voucher[inv["return_voucher_no"]]
                    self.assertTrue(rows and ret_rows, "invoice and credit note must both post")
                    self.assertTrue(has_amount(rows) and has_amount(ret_rows))
                    self.assertFalse(mirror_mismatch(rows + ret_rows))
                    self.assertEqual(Decimal(inv["return_totals"]["taxes"]), -Decimal(inv["totals"]["taxes"]))
                    self.assertEqual(Decimal(inv["return_totals"]["grand_total"]),
                                     -Decimal(inv["totals"]["grand_total"]))
                else:
                    self.assertTrue(mirror_mismatch(rows), "a kept invoice must not be reversed")

    def test_5_stock_value_ties_to_stock_in_hand(self):
        st, moves = self.data["stock"], self.inputs["stock_moves"]
        steps = st["steps"]
        self.assertEqual(len(steps), 1 + len(moves), "the opening receipt plus every move must post")
        self.assertEqual((Decimal(steps[0]["qty"]), Decimal(steps[0]["value"])), (100, Decimal("1000.00")))
        self.assertEqual((Decimal(steps[1]["qty"]), Decimal(steps[1]["value"])), (90, Decimal("900.00")))
        expected = expected_stock_steps(moves)  # exact Moving Average in Decimal: FIFO would differ from step 3 on
        for i, (step, (qty, value)) in enumerate(zip(steps, expected)):
            with self.subTest(step=i):
                self.assertGreater(qty, 0)
                self.assertEqual(Decimal(step["qty"]), qty)
                # the engine stores the value at currency precision, so allow one cent, far below any FIFO gap
                self.assertLessEqual(abs(Decimal(step["value"]) - value), CENT)
        self.assertEqual(Decimal(st["bin_qty"]), expected[-1][0])
        self.assertLessEqual(abs(Decimal(st["bin_value"]) - expected[-1][1]), CENT)
        self.assertEqual(Decimal(st["bin_value"]), Decimal(st["sle_value"]))
        self.assertEqual(Decimal(st["bin_value"]), Decimal(st["gl_stock_in_hand"]))


if __name__ == "__main__":
    unittest.main()
