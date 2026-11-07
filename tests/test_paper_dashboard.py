"""Offline tests for deterministic indicators and non-executing HTML."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from paper_dashboard import build_dashboard, indicators


def candles(prices):
    start=1800000000000-len(prices)*3600000
    return [{"end_ms":start+(i+1)*3600000-1,"close":float(p)} for i,p in enumerate(prices)]


class TestPaperDashboard(unittest.TestCase):
    def test_neutral_when_flat(self):
        value=indicators(candles([100]*60))
        self.assertEqual(value["rsi"],50)
        self.assertEqual(value["watch"],"MIXED")
        self.assertEqual(sum(abs(x) for x in value["votes"].values()),0)

    def test_uptrend(self):
        value=indicators(candles([100+i for i in range(60)]))
        self.assertEqual(value["rsi"],100)
        self.assertEqual(value["watch"],"BULLISH_WATCH")
        self.assertNotIn("win_probability",value)

    def test_downtrend(self):
        value=indicators(candles([200-i for i in range(60)]))
        self.assertEqual(value["rsi"],0)
        self.assertEqual(value["watch"],"BEARISH_WATCH")

    def test_reject_short_and_nonfinite(self):
        for sample in ([100]*29,[100]*29+[float("nan")]):
            with self.assertRaises(ValueError):
                indicators(candles(sample))

    def test_offline_html_and_escaped_data(self):
        prices=candles([100+i for i in range(60)])
        market="Binance </script><script>alert(1)</script>"
        account={"cash":10000.0,"units":0.0,"stop_price":0.0,
                 "last_candle_ms":prices[-1]["end_ms"],"trades":0}
        with TemporaryDirectory() as temp:
            page=build_dashboard({"binance":{"name":market,"candles":prices,
                                               "state":account}},Path(temp),1800000000000)
            self.assertIn("BULLISH_WATCH",page)
            self.assertIn("VIRTUAL MONEY ONLY",page)
            self.assertIn("\\u003c/script\\u003e",page)
            self.assertNotIn("</script><script>alert",page)
            self.assertNotIn("fetch(",page)
            self.assertNotIn("<button",page)


if __name__=="__main__":
    unittest.main()
