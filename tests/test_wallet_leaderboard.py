"""Offline wallet leaderboard tests. No exchange auth or orders."""
import unittest
from unittest.mock import patch
from tempfile import TemporaryDirectory
from pathlib import Path

import wallet_leaderboard as wl
from bot import MarketDataError

ADDR = "0x" + "a" * 40


def row(address=ADDR, pnl=30000, roi=0.3, equity=50000, volume=300000):
    return {"ethAddress": address, "accountValue": str(equity),
            "windowPerformances": [[w, {"pnl": str(pnl),
                                         "roi": str(roi),
                                         "vlm": str(volume)}]
                                   for w in ("day", "week", "month")]}


class WalletBoardTests(unittest.TestCase):
    def test_shortlist_requires_all_three_positive_windows(self):
        result = wl.shortlist([row()])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["address"], ADDR)
        bad = row(address="0x" + "b" * 40)
        bad["windowPerformances"][0][1]["pnl"] = "-10"
        self.assertEqual(wl.shortlist([bad]), [])

    def test_rejects_extreme_roi_and_small_liquidity(self):
        self.assertEqual(wl.shortlist([row(roi=99)]), [])
        self.assertEqual(wl.shortlist([row(equity=1)]), [])
        self.assertEqual(wl.shortlist([row(volume=1)]), [])

    def test_wallet_deduplication_and_limit(self):
        other = row(address="0x" + "b" * 40, pnl=8000)
        result = wl.shortlist([row(), row(), other], limit=2)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["address"], ADDR)

    def test_public_fills_api_only(self):
        with patch.object(wl, "read_json", return_value=[
            {"time": 1800000000000, "coin": "BTC", "dir": "Open Long", "px": "1", "sz": "2"}
        ]) as mock:
            rows = wl.recent_fills(wl.shortlist([row()]), 1800000000000)
        self.assertEqual(len(rows[0]["fills"]), 1)
        self.assertEqual(mock.call_args.args[1]["type"], "userFills")
        self.assertEqual(mock.call_args.args[1]["user"], ADDR)

    def test_report_explicit_no_real_trading(self):
        txt = wl.report(wl.shortlist([row()]), [], 1800000000000)
        self.assertIn("NO REAL ORDERS", txt)
        self.assertIn("NO COPY TRADING", txt)
        self.assertIn(ADDR, txt)

    def test_bad_board_fails_closed(self):
        with self.assertRaises(MarketDataError):
            wl.shortlist({})
        with patch.object(wl, "load_public_board", side_effect=MarketDataError("offline")):
            with TemporaryDirectory() as d:
                with self.assertRaises(MarketDataError):
                    wl.main(Path(d), 1800000000000)
                self.assertFalse((Path(d) / "research" / "WALLETS.md").exists())
