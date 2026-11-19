import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import plan_review as p  # noqa: E402


def row(i, status, gate="G1", deps="-", owner="eldon"):
    return {"ID": i, "Status": status, "Gate": gate, "Depends": deps, "Owner": owner}


ROWS = [row("A-001", "done"), row("A-002", "doing"), row("A-003", "doing"), row("A-004", "todo", deps="A-001"),
        row("A-005", "todo", deps="A-002", owner="partner"), row("A-006", "blocked"),
        row("A-007", "todo", gate="G1", deps="A-008"), row("A-008", "todo", gate="G2")]


def test_stale_doing_needs_a_recent_log():
    out = p.review(ROWS, {"A-002"}, "G1")
    assert out["stale_doing"] == ["A-003"]


def test_ready_rows_grouped_by_owner_and_deps_done():
    out = p.review(ROWS, set(), "G1")
    assert out["ready"] == {"eldon": ["A-004", "A-008"]}
    assert "A-005" not in out["ready"].get("partner", [])


def test_gate_inversion_and_blocked_and_open_rows():
    out = p.review(ROWS, set(), "G1")
    assert out["gate_inversions"] == ["A-007 (G1) depends on A-008 (G2)"]
    assert out["blocked"] == ["A-006"]
    assert "A-001 [done, eldon]" not in out["open_in_gate"]


def test_render_is_deterministic():
    out = p.review(ROWS, set(), "G1")
    assert p.render(out, "G1", 5) == p.render(out, "G1", 5)
