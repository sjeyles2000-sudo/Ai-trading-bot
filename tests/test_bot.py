"""Safety-focused tests: only public read-only prices, no real order interfaces."""
import unittest
from unittest.mock import patch
from urllib.error import URLError
import bot

NOW = 1800000000000


def sample_candles(n=30, price=100.0):
    start = NOW - n * bot.INTERVAL_MS
    return [{"end_ms": start + (i + 1) * bot.INTERVAL_MS - 1,
             "open": price, "high": price + 2, "low": price - 2,
             "close": price} for i in range(n)]


class PaperTradingTests(unittest.TestCase):
    def test_binance_uses_public_candles(self):
        rows = [[c["end_ms"] - bot.INTERVAL_MS + 1, str(c["open"]),
                 str(c["high"]), str(c["low"]), str(c["close"]), "12",
                 c["end_ms"]] for c in sample_candles()]
        with patch.object(bot, "read_json", return_value=rows) as reader:
            data = bot.fetch_binance(NOW)
        self.assertEqual(len(data), 30)
        self.assertIn("/klines?", reader.call_args.args[0])
        self.assertNotIn("apiKey", reader.call_args.args[0])

    def test_hyperliquid_uses_read_only_info(self):
        rows = [{"T": c["end_ms"], "o": c["open"], "h": c["high"],
                 "l": c["low"], "c": c["close"]} for c in sample_candles()]
        with patch.object(bot, "read_json", return_value=rows) as reader:
            data = bot.fetch_hyperliquid(NOW)
        self.assertEqual(len(data), 30)
        self.assertTrue(reader.call_args.args[0].endswith("/info"))
        self.assertEqual(reader.call_args.args[1]["type"], "candleSnapshot")

    def test_rejects_invalid_and_stale_prices(self):
        with self.assertRaises(bot.MarketDataError):
            bot.validate_candles([{"end_ms": 0, "open": 0, "high": 1,
                                   "low": 1, "close": 1}], NOW)
        with self.assertRaises(bot.MarketDataError):
            bot.validate_candles(sample_candles(), NOW + 5 * bot.INTERVAL_MS)

    def test_rejects_five_minute_candles_mislabeled_as_hourly(self):
        candles = sample_candles()
        five_minutes_ms = bot.INTERVAL_MS // 12
        for i, candle in enumerate(candles):
            candle["end_ms"] = NOW - (len(candles) - i) * five_minutes_ms - 1
        with self.assertRaisesRegex(bot.MarketDataError, "Non-hourly"):
            bot.validate_candles(candles, NOW)

    def test_accepts_small_hourly_timestamp_drift(self):
        candles = sample_candles()
        candles[10]["end_ms"] += 500
        self.assertEqual(len(bot.validate_candles(candles, NOW)), 30)

    def test_ignores_incomplete_candle(self):
        rows = sample_candles()
        rows.append({**rows[-1], "end_ms": NOW + bot.INTERVAL_MS})
        self.assertEqual(len(bot.validate_candles(rows, NOW)), 30)

    def test_network_error_fails_closed(self):
        with patch.object(bot, "urlopen", side_effect=URLError("offline")):
            with self.assertRaises(bot.MarketDataError):
                bot.read_json(bot.BINANCE_URL)

    def test_simulated_trades_only(self):
        candles = sample_candles(70)
        for i, c in enumerate(candles):
            p = 100 - i * 0.2 if i < 30 else (94 + (i - 30) * 0.5 if i < 50 else 104 - (i - 50) * 0.6)
            c.update(open=p, high=p + 1, low=p - 1, close=p)
        stats = bot.simulate("test", candles, verbose=False)
        self.assertGreaterEqual(stats["trades"], 2)
        self.assertGreater(stats["equity"], 0)
        self.assertLessEqual(stats["units"] * candles[-1]["close"], stats["equity"])


if __name__ == "__main__":
    unittest.main()
