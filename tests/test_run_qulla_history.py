"""Synthetic no-network tests for the isolated historical research runner."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from bot import MarketDataError
from qulla_breakout_lab import DAY_MS
from run_qulla_history import fetch_daily, passive_reference, run


NOW = 1_803_000_000_000


def bars(count=600):
    start = NOW-(count+2)*DAY_MS
    return [{
        "end_ms": start+(i+1)*DAY_MS-1,
        "open": 100.0, "high": 101.0, "low": 99.0,
        "close": 100.0, "volume": 10.0,
    } for i in range(count)]


class DailyPublicDataRunnerTests(unittest.TestCase):
    def test_binance_uses_public_daily_spot_klines(self):
        history = bars()
        rows = [[b["end_ms"]-DAY_MS+1, str(b["open"]), str(b["high"]),
                 str(b["low"]), str(b["close"]), str(b["volume"]),
                 b["end_ms"]] for b in history]
        with patch("run_qulla_history.read_json", return_value=rows) as read:
            out=fetch_daily("binance","BTC",NOW)
        self.assertEqual(len(out), len(rows))
        self.assertIn("interval=1d", read.call_args.args[0])
        self.assertNotIn("apiKey", read.call_args.args[0])

    def test_hyperliquid_is_public_info_only(self):
        history = bars()
        rows = [{"T":b["end_ms"],"o":b["open"],"h":b["high"],
                 "l":b["low"],"c":b["close"],"v":b["volume"]}
                for b in history]
        with patch("run_qulla_history.read_json", return_value=rows) as read:
            out=fetch_daily("hyperliquid","ETH",NOW)
        self.assertEqual(len(out),len(rows))
        self.assertTrue(read.call_args.args[0].endswith("/info"))
        self.assertEqual(read.call_args.args[1]["type"],"candleSnapshot")
        self.assertEqual(read.call_args.args[1]["req"]["interval"],"1d")

    def test_stale_or_incomplete_feed_rejected(self):
        old = bars()
        with patch("run_qulla_history.read_json", return_value=[
                [b["end_ms"]-DAY_MS+1, str(b["open"]), str(b["high"]),
                 str(b["low"]), str(b["close"]), str(b["volume"]),
                 b["end_ms"]] for b in old]):
            with self.assertRaises(MarketDataError):
                fetch_daily("binance","BTC",NOW+DAY_MS*12)

    def test_passive_reference_costs_on_flat_btc(self):
        self.assertLess(passive_reference(bars(),420),0)
        self.assertGreater(passive_reference(bars(),420),-0.01)

    def test_all_four_research_rows_and_no_ledger_mutation(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/"research"/"daily.md"
            report=run(path,NOW,lambda venue,asset,now: bars())
            self.assertTrue(path.exists())
            self.assertEqual(report.count("| binance "),2)
            self.assertEqual(report.count("| hyperliquid "),2)
            self.assertIn("Holdout max DD",report)
            self.assertFalse((Path(directory)/"ledger").exists())

    def test_failed_market_prevents_partial_report(self):
        def fetch(venue,asset,now):
            if venue=="hyperliquid":
                raise MarketDataError("fake feed outage")
            return bars()
        with TemporaryDirectory() as directory:
            dest=Path(directory)/"daily.md"
            with self.assertRaises(MarketDataError):
                run(dest,NOW,fetch)
            self.assertFalse(dest.exists())

    def test_invalid_market_cannot_request_data(self):
        with self.assertRaises(ValueError):
            fetch_daily("unknown","BTC",NOW)


if __name__=="__main__":
    unittest.main()
