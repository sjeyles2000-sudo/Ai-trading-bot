"""Offline regression tests for read-only short-term strategy comparisons."""
import math
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from short_term_lab import (STRATEGIES, START_CASH, compare, ema, fetch_history,
                            passive_btc_reference, report, run, signals,
                            simulate, validate)
from bot import MarketDataError

START = 1793491200000


def fixture(strategy="scalp_5m", count=350, opening=100., high=100.1,
            low=99.9, close=100., volume=100.):
    duration = STRATEGIES[strategy][1]
    return [{"end_ms": START + duration*(i+1), "open": opening,
             "high": high, "low": low, "close": close, "volume": volume}
            for i in range(count)]


def override(count, entry_index=40, exit_index=45):
    buy, sell, explanations = [False]*count, [False]*count, [""]*count
    buy[entry_index], sell[exit_index] = True, True
    explanations[entry_index] = "Test confirmed candle"
    return buy, sell, explanations


class StrategyLabTests(unittest.TestCase):
    def test_flat_market_no_trades(self):
        for strategy in STRATEGIES:
            with self.subTest(strategy=strategy):
                result = simulate(fixture(strategy), strategy)
                self.assertEqual(result["closed_trades"], 0)
                self.assertEqual(result["return_pct"], 0)
                self.assertEqual(result["max_drawdown_pct"], 0)
                self.assertIsNone(result["win_rate_pct"])

    def test_signals_enter_at_next_open_only(self):
        bars = fixture()
        result = simulate(bars, "scalp_5m", signal_override=override(len(bars)))
        buys = [event for event in result["events"] if event[1].startswith("BUY")]
        sells = [event for event in result["events"] if event[1] == "SIGNAL EXIT"]
        self.assertEqual(len(buys), 1)
        self.assertEqual(buys[0][0], 41)
        self.assertEqual(sells[0][0], 46)
        self.assertLess(result["return_pct"], 0)  # fees + slippage

    def test_entry_bar_stop_conservative(self):
        bars = fixture(low=99.0)
        result = simulate(bars, "scalp_5m", signal_override=override(len(bars)))
        self.assertIn("ENTRY BAR STOP", [e[1] for e in result["events"]])
        self.assertLess(result["return_pct"], 0)

    def test_invalid_and_gapped_bars_fail_closed(self):
        bars = fixture()
        bad = [dict(x) for x in bars]
        bad[80]["end_ms"] += 5*60*1000
        with self.assertRaises(MarketDataError):
            validate(bad, STRATEGIES["scalp_5m"][1])
        bad = [dict(x) for x in bars]
        bad[80]["volume"] = float("nan")
        with self.assertRaises(MarketDataError):
            validate(bad, STRATEGIES["scalp_5m"][1])
        bad = [dict(x) for x in bars]
        bad[80]["high"] = 90.0
        with self.assertRaises(MarketDataError):
            validate(bad, STRATEGIES["scalp_5m"][1])

    def test_fixed_holdout_separate_from_training(self):
        bars = fixture()
        results = compare(bars, "scalp_5m")
        self.assertEqual(results["split"], 245)
        self.assertEqual(len(results["train"]["equity"]), 245-32)
        self.assertEqual(len(results["holdout"]["equity"]), 350-245)
        self.assertEqual(results["holdout"]["return_pct"], 0.0)

    def test_passive_reference_flat_prices_pay_costs(self):
        bars = fixture()
        result = passive_btc_reference(bars, 245, len(bars))
        self.assertEqual(result["btc_price_change_pct"], 0)
        self.assertLess(result["return_pct"], 0)
        # Two-sided costs on a 2% account allocation, not on $10,000.
        self.assertGreater(result["return_pct"], -0.01)

    def test_passive_reference_uptrend_and_window_boundaries(self):
        bars = fixture(count=350)
        for i, bar in enumerate(bars):
            price = 100 + 0.01*i
            bar.update(open=price, high=price+0.1,
                       low=price-0.1, close=price)
        result = passive_btc_reference(bars, 245, 350)
        self.assertGreater(result["btc_price_change_pct"], 0)
        self.assertGreater(result["return_pct"], 0)
        with self.assertRaises(ValueError):
            passive_btc_reference(bars, 350, 350)

    def test_compare_includes_cost_aware_reference_without_extra_trades(self):
        bars = fixture()
        result = compare(bars, "scalp_5m")
        self.assertEqual(result["holdout"]["closed_trades"], 0)
        self.assertLess(result["passive_reference"]["return_pct"], 0)
        self.assertAlmostEqual(
            result["excess_vs_passive_pct_points"],
            result["holdout"]["return_pct"]-result["passive_reference"]["return_pct"])

    def test_three_holdout_windows_do_not_overlap(self):
        bars = fixture(count=1200)
        result = compare(bars, "scalp_5m")
        self.assertEqual(len(result["windows"]), 3)
        windows = result["windows"]
        self.assertEqual(windows[0]["start"], result["split"])
        self.assertEqual(windows[-1]["end"], len(bars))
        for first, second in zip(windows, windows[1:]):
            self.assertEqual(first["end"], second["start"])
        for window in windows:
            self.assertGreaterEqual(window["end"] - window["start"], 90)
            self.assertEqual(len(window["stats"]["equity"]),
                             window["end"] - window["start"])
            self.assertEqual(window["stats"]["closed_trades"], 0)
            self.assertEqual(window["stats"]["return_pct"], 0)

    def test_insufficient_bars_do_not_fake_stability_results(self):
        result = compare(fixture(count=350), "scalp_5m")
        self.assertEqual(result["windows"], [])

    def test_15m_engulfing_requires_trend_filter(self):
        bars = fixture("engulf_15m")
        # Pattern bullish but below its EMA trend must be rejected.
        bars[49].update(open=101., close=99.9, high=101.2, low=99.8)
        bars[50].update(open=99.8, close=101.1, high=101.2, low=99.7)
        buy, _, _ = signals(bars, "engulf_15m")
        self.assertTrue(buy[50])
        self.assertFalse(buy[49])

    def test_failed_exchange_prevents_report_write(self):
        def feeds(market, strategy, now_ms):
            if market == "hyperliquid":
                raise MarketDataError("Unavailable")
            return fixture(strategy)
        with TemporaryDirectory() as temp:
            dest = Path(temp)/"backtest-results"/"short-term.md"
            with self.assertRaises(MarketDataError):
                run(dest, START, feeds)
            self.assertFalse(dest.exists())
            self.assertFalse((Path(temp)/"ledger").exists())

    def test_four_cases_generate_one_isolated_report(self):
        def feeds(market, strategy, now_ms):
            return fixture(strategy)
        with TemporaryDirectory() as temp:
            dest = Path(temp)/"backtest-results"/"short-term.md"
            results = run(dest, START, feeds)
            self.assertEqual(len(results), 4)
            text = dest.read_text(encoding="utf-8")
            self.assertIn("HISTORICAL", text)
            self.assertIn("holdout", text)
            self.assertIn("Critical review", text)
            self.assertIn("doubled trading costs", text)
            self.assertFalse((Path(temp)/"ledger").exists())

    def test_fetch_rejects_stale_and_never_needs_credentials(self):
        rows = [[0]*12 for _ in range(350)]
        duration = STRATEGIES["scalp_5m"][1]
        for i, row in enumerate(rows):
            row[1], row[2], row[3], row[4], row[5] = "100", "101", "99", "100", "10"
            row[6] = START + duration*(i+1)
        with patch("short_term_lab.read_json", return_value=rows):
            bars = fetch_history("binance", "scalp_5m", rows[-1][6]+duration)
            self.assertEqual(len(bars), 350)
            with self.assertRaises(MarketDataError):
                fetch_history("binance", "scalp_5m", rows[-1][6] + duration*10)

    def test_ema_and_report_are_deterministic(self):
        self.assertEqual(ema([100.]*10, 8), [100.]*10)
        inputs = {}
        for market in ("binance", "hyperliquid"):
            for strategy in STRATEGIES:
                bars = fixture(strategy)
                result = compare(bars, strategy)
                result["history_count"] = len(bars)
                result["stress_holdout"] = simulate(
                    bars, strategy, first_bar=result["split"],
                    fee_pct=.002, slippage_pct=.001)
                inputs[(market, strategy)] = result
        rendered = report(inputs, START)
        self.assertEqual(rendered.count("| holdout |"), 4)
        self.assertIn("no real orders", rendered)
        self.assertIn("N/A", rendered)


    def test_cost_stress_is_worse_for_trades(self):
        bars = fixture()
        base = simulate(bars, "scalp_5m", signal_override=override(len(bars)))
        stress = simulate(bars, "scalp_5m", signal_override=override(len(bars)),
                          fee_pct=.002, slippage_pct=.001)
        self.assertLess(stress["return_pct"], base["return_pct"])
        self.assertEqual(base["closed_trades"], stress["closed_trades"])

    def test_pagination_of_1000_binance_candles(self):
        duration = STRATEGIES["scalp_5m"][1]
        all_rows = []
        for i in range(3500):
            row = [0]*12
            row[0] = START + duration*i
            row[1], row[2], row[3], row[4], row[5] = (
                "100", "101", "99", "100", "10")
            row[6] = row[0] + duration - 1
            all_rows.append(row)
        now_ms = all_rows[-1][6] + 1
        calls = []
        def fake_read_json(url, payload=None):
            from urllib.parse import parse_qs, urlparse
            params = parse_qs(urlparse(url).query)
            end = int(params["endTime"][0])
            limit = int(params["limit"][0])
            calls.append((end, limit))
            available = [row for row in all_rows if row[0] <= end]
            return available[-limit:]
        with patch("short_term_lab.read_json", side_effect=fake_read_json):
            bars = fetch_history("binance", "scalp_5m", now_ms)
        self.assertEqual(len(bars), 3500)
        self.assertGreaterEqual(len(calls), 4)
        self.assertEqual(bars[0]["end_ms"], all_rows[0][6])
        self.assertEqual(bars[-1]["end_ms"], all_rows[-1][6])



if __name__ == "__main__":
    unittest.main()
