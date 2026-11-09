"""Deterministic tests for read-only Elysium research screening."""
import unittest
from datetime import datetime, timezone, timedelta

from elysium_watch import evaluate, build_report

NOW = datetime(2026, 11, 10, 0, 0, tzinfo=timezone.utc)


def valid(project="STOCKIUM"):
    return {
        "project": project,
        "source_url": "https://example.org/independent-review",
        "chain": "elysium",
        "contract_address": "verified-contract-example",
        "observed_at": (NOW - timedelta(minutes=10)).isoformat(),
        "liquidity_usd": 100000,
        "volume_24h_usd": 50000,
        "top10_holder_pct": 25,
        "round_trip_cost_pct": 1.5,
        "sell_simulation_verified": True,
        "contract_permissions_reviewed": True,
    }


class ElysiumWatchTests(unittest.TestCase):
    def test_valid_is_only_research_screen_pass(self):
        result = evaluate(valid(), NOW)
        self.assertEqual(result["status"], "RESEARCH SCREEN PASS")
        self.assertIn("NOT investment", result["reasons"][0])

    def test_missing_metrics_fail_closed(self):
        row = valid()
        del row["liquidity_usd"]
        self.assertEqual(evaluate(row, NOW)["status"], "NOT READY")

    def test_liquidity_holder_and_cost_gates(self):
        row = valid()
        row.update(liquidity_usd=12000, top10_holder_pct=61.5, round_trip_cost_pct=5)
        result = evaluate(row, NOW)
        self.assertEqual(result["status"], "NOT READY")
        self.assertGreaterEqual(len(result["reasons"]), 3)

    def test_stale_snapshot_rejected(self):
        row = valid()
        row["observed_at"] = (NOW - timedelta(hours=3)).isoformat()
        self.assertIn("Stale or future-dated snapshot", evaluate(row, NOW)["reasons"])

    def test_no_source_sell_test_or_contract_review(self):
        row = valid()
        row["source_url"] = "http://unsafe"
        row["sell_simulation_verified"] = False
        row["contract_permissions_reviewed"] = False
        self.assertEqual(evaluate(row, NOW)["status"], "NOT READY")

    def test_duplicate_or_unrecognized_fails(self):
        with self.assertRaises(ValueError):
            build_report([valid(), valid()], NOW)
        with self.assertRaises(ValueError):
            evaluate(valid("OTHER"), NOW)

    def test_default_report_marks_all_unverified(self):
        report = build_report([], NOW)
        for name in ("STOCKIUM", "BOXA", "ASCEND"):
            self.assertIn(f"| {name} | NOT READY |", report)
        self.assertIn("NO ORDERS", report)

    def test_invalid_number_not_accepted(self):
        row = valid()
        row["volume_24h_usd"] = float("nan")
        self.assertEqual(evaluate(row, NOW)["status"], "NOT READY")


if __name__ == "__main__":
    unittest.main()
