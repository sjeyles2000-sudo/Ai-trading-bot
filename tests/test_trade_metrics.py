"""Offline Node assertions for the read-only paper ledger calculations."""
import json
from pathlib import Path
import subprocess
import unittest

MODULE = Path(__file__).resolve().parents[1] / "docs" / "trade-metrics.js"


def calculate(rows):
    program = """
const {summarize} = require(process.argv[1]);
const rows = JSON.parse(process.argv[2]);
try {
  process.stdout.write(JSON.stringify({ok:true, result:summarize(rows, "Binance BTC/USDT spot")}));
} catch (error) {
  process.stdout.write(JSON.stringify({ok:false, message:error.message}));
}
"""
    proc = subprocess.run(
        ["node", "-e", program, str(MODULE), json.dumps(rows)],
        check=True, capture_output=True, text=True, timeout=10,
    )
    return json.loads(proc.stdout)


def event(side, price, quantity="1.00000000", fee="0.10"):
    return {"market": "Binance BTC/USDT spot", "side": side,
            "quantity_btc": quantity, "virtual_price_usd": str(price),
            "virtual_fee_usd": fee}


class TradeMetricsTests(unittest.TestCase):
    def test_win_loss_and_net_fee_calculation(self):
        trades = [event("BUY", 100), event("SIGNAL SELL", 110),
                  event("BUY", 100), event("STOP SELL", 90)]
        result = calculate(trades)
        self.assertTrue(result["ok"])
        stats = result["result"]
        self.assertEqual(stats["closed"], 2)
        self.assertEqual(stats["transactions"], 4)
        self.assertEqual(stats["wins"], 1)
        self.assertEqual(stats["winRate"], 50)
        self.assertAlmostEqual(stats["fees"], 0.4)
        self.assertAlmostEqual(stats["net"], -0.4)
        self.assertAlmostEqual(stats["profitFactor"], 9.8 / 10.2)

    def test_missing_closed_trade_not_fabricated(self):
        stats = calculate([event("BUY", 100)])["result"]
        self.assertEqual(stats["closed"], 0)
        self.assertIsNone(stats["winRate"])
        self.assertIsNone(stats["profitFactor"])
        self.assertTrue(stats["hasOpenPosition"])

    def test_no_trades_not_a_hundred_percent_win_rate(self):
        stats = calculate([])["result"]
        self.assertIsNone(stats["winRate"])
        self.assertIsNone(stats["profitFactor"])
        self.assertEqual(stats["net"], 0)

    def test_corrupt_and_mismatched_ledger_rejected(self):
        for rows in (
            [event("SIGNAL SELL", 100)],
            [event("BUY", 100), event("BUY", 101)],
            [event("BUY", 100), event("SIGNAL SELL", 110, quantity="0.5")],
            [event("BUY", 100, fee="NaN")],
            [event("BUY", 100, fee="")],
            [event("BUY", 100, quantity="0")],
            [event("BUY", 100), event("UNKNOWN", 110)],
        ):
            with self.subTest(rows=rows):
                self.assertFalse(calculate(rows)["ok"])

    def test_other_market_does_not_affect_stats(self):
        unrelated = dict(event("BUY", 100), market="Hyperliquid BTC perpetual")
        stats = calculate([unrelated])["result"]
        self.assertEqual(stats["transactions"], 0)


if __name__ == "__main__":
    unittest.main()
