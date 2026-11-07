"""Read-only research signals tests using fixture data, no exchange orders."""
import unittest
from unittest.mock import patch
from tempfile import TemporaryDirectory
from pathlib import Path
from bot import MarketDataError
import research_radar as radar

NOW = 1800000000000


class ResearchRadarTests(unittest.TestCase):
    def test_fomo_flag_is_not_a_buy(self):
        prices = [100.0] * 26
        prices[-4:] = [100.0, 101.0, 103.0, 105.0]
        volumes = [10.0] * 25 + [50.0]
        signal = radar.fomo_signal(prices, volumes)
        self.assertEqual(signal["signal"], "FOMO_RISK")
        self.assertNotIn("BUY", str(signal))

    def test_bullish_watch(self):
        prices = [100.0] * 25 + [101.0]
        volumes = [10.0] * 25 + [25.0]
        self.assertEqual(radar.fomo_signal(prices, volumes)["signal"], "BULLISH_WATCH")

    def test_rejects_bad_volumes(self):
        with self.assertRaises(MarketDataError):
            radar.fomo_signal([100.] * 25, [1.] * 24 + [float("nan")])

    def test_cautious_meme_age_and_liquidity_screen(self):
        profile = [{"chainId": "solana", "tokenAddress": "SAMPLE"}]
        def lookup(chain, addr):
            return [{"baseToken": {"address": addr, "symbol": "MEME"},
                     "pairCreatedAt": NOW - 10 * 3600000,
                     "liquidity": {"usd": 90000},
                     "volume": {"h24": 15000}, "priceUsd": "0.001"}]
        tokens = radar.candidates_from_profiles(profile, NOW, lookup)
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0]["symbol"], "MEME")
        def unsafe(chain, addr):
            p = lookup(chain, addr)
            p[0]["liquidity"]["usd"] = 100
            return p
        self.assertEqual(radar.candidates_from_profiles(profile, NOW, unsafe), [])

    def test_invalid_wallet_rejected_before_fetch(self):
        with patch.object(radar, "read_json") as reader:
            with self.assertRaises(MarketDataError):
                radar.wallet_fills(["not-a-wallet"], NOW)
        reader.assert_not_called()

    def test_wallet_public_fills_are_recent_only(self):
        address = "0x" + "a" * 40
        fills = [{"time": NOW - 3600000, "coin": "BTC", "dir": "Open Long",
                  "px": "70000", "sz": "0.1"},
                 {"time": NOW - 25 * 3600000, "coin": "ETH", "dir": "Buy",
                  "px": "2000", "sz": "1"}]
        with patch.object(radar, "read_json", return_value=fills) as reader:
            rows = radar.wallet_fills([address], NOW)
        self.assertEqual(len(rows), 1)
        self.assertEqual(reader.call_args.args[1]["type"], "userFills")

    def test_report_labels_research_only(self):
        report = radar.create_report(NOW, {}, [], [], {})
        self.assertIn("NO REAL TRADES", report)
        self.assertIn("Not checked", report)
        self.assertNotIn("PAPER BUY", report)

    def test_no_wallets_makes_no_wallet_api_calls(self):
        with patch.object(radar, "read_json") as reader:
            self.assertEqual(radar.wallet_fills([], NOW), [])
        reader.assert_not_called()


if __name__ == "__main__":
    unittest.main()
