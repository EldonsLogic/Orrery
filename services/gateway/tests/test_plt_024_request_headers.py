"""PLT-024 (ADR-0016): request headers reaching the engine are allow-list only; identity never comes from the caller."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from gateway.edge.headers import request_headers_for_engine  # noqa: E402

BLOCKED = [
    "X-Frappe-Site-Name", "Host", "Forwarded", "Cookie", "Authorization",
    "X-Forwarded-For", "X-Forwarded-Host", "X-Forwarded-Proto", "X-Forwarded-Port", "X-Forwarded-User",
    "X-Forwarded-Unknown-Suffix", "X-Forwarded-",
]
ALLOWED = [("Accept", "application/json"), ("Accept-Language", "ar"), ("Content-Type", "application/json"),
           ("Idempotency-Key", "k-1")]


def casings(name: str) -> list[str]:
    return [name, name.lower(), name.upper(), name.swapcase()]


class RequestHeaderAllowListTests(unittest.TestCase):
    def test_blocked_headers_never_reach_engine_in_any_casing(self):
        for base in BLOCKED:
            for name in casings(base):
                with self.subTest(header=name):
                    self.assertEqual(request_headers_for_engine([(name, "synthetic-value")]), [])

    def test_blocked_headers_dropped_while_allowed_pass(self):
        mixed = [(n, "x") for b in BLOCKED for n in casings(b)] + ALLOWED
        self.assertEqual(request_headers_for_engine(mixed), ALLOWED)

    def test_allowed_headers_pass_in_any_casing_with_original_name_and_value(self):
        for name, value in ALLOWED:
            for variant in casings(name):
                with self.subTest(header=variant):
                    self.assertEqual(request_headers_for_engine([(variant, value)]), [(variant, value)])

    def test_input_is_left_unmodified(self):
        headers = [("Cookie", "sid=abc"), ("Authorization", "Bearer t"), ("Host", "h"), ("Accept", "*/*")]
        snapshot = list(headers)
        request_headers_for_engine(headers)
        self.assertEqual(headers, snapshot)

    def test_empty_input(self):
        self.assertEqual(request_headers_for_engine([]), [])


if __name__ == "__main__":
    unittest.main()
