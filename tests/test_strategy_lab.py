"""Offline safety tests for both isolated paper strategy candidates."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import strategy_lab as lab


def synthetic(prices):
    base = 1_790_000_000_000
    return [dict(end_ms=base+(i+1)*lab.HOUR-1, open=float(price),
                 high=float(price)*1.005, low=float(price)*.995,
                 close=float(price)) for i,price in enumerate(prices)]


class StrategyLabTests(unittest.TestCase):
    def test_flat_market_no_fake_profit(self):
        bars = synthetic([100]*800)
        result=lab.compare(bars)
        for name in lab.STRATEGIES:
            self.assertEqual(result[name]["holdout"]["return_pct"], 0)
            self.assertEqual(result[name]["holdout"]["closed"], 0)
        self.assertLess(result["benchmarks"]["2pct_btc_holdout_pct"], 0)

    def test_signals_do_not_peek_future(self):
        bars=synthetic([100+.05*i+1.5*(i%13==0) for i in range(800)])
        for strategy in lab.STRATEGIES:
            a,b=lab.signals(bars,strategy)
            altered=[dict(x) for x in bars]
            altered[-1]["open"] += 20
            altered[-1]["high"] += 40
            altered[-1]["close"] += 20
            c,d=lab.signals(altered,strategy)
            self.assertEqual(a[:-1],c[:-1])
            self.assertEqual(b[:-1],d[:-1])

    def test_reject_missing_candle_and_nonfinite(self):
        bars=synthetic([100]*800)
        wrong=[dict(x) for x in bars]
        wrong[50]["end_ms"] += 120000
        with self.assertRaises(lab.MarketDataError):
            lab.validate(wrong)
        wrong=[dict(x) for x in bars]
        wrong[60]["close"]=float("nan")
        with self.assertRaises(lab.MarketDataError):
            lab.validate(wrong)

    def test_invalid_fee_settings_and_strategies(self):
        bars=synthetic([100]*800)
        with self.assertRaises(ValueError):
            lab.simulate(bars,"breakout",fee=-.01)
        with self.assertRaises(ValueError):
            lab.simulate(bars,"anything")
        with self.assertRaises(ValueError):
            lab.simulate(bars,"pullback",first=600,last=600)

    def test_all_candidates_on_trending_and_choppy_bars(self):
        prices=[100+.025*i+2*((i%10)-5)/10 for i in range(800)]
        result=lab.compare(synthetic(prices))
        for name in lab.STRATEGIES:
            for key in ("train","holdout","stress"):
                r=result[name][key]
                self.assertLessEqual(r["max_dd_pct"],100)
                self.assertGreaterEqual(r["closed"],0)
                self.assertTrue(isinstance(r["return_pct"],float))

    def test_binance_pagination_four_thousand(self):
        from urllib.parse import parse_qs,urlsplit
        now=1_800_000_000_000
        first=now-4005*lab.HOUR
        candles=[]
        for i in range(4005):
            t=first+i*lab.HOUR
            candles.append([t,"100","101","99","100","0",t+lab.HOUR-1])
        queries=[]
        def read(url):
            args=parse_qs(urlsplit(url).query)
            limit=int(args["limit"][0])
            cursor=int(args["endTime"][0])
            queries.append(cursor)
            return [r for r in candles if r[0]<=cursor][-limit:]
        result=lab.fetch("binance",now,read)
        self.assertEqual(len(result),lab.BARS)
        self.assertEqual(len(queries),5)
        self.assertEqual(result[-1]["end_ms"],now-1)

    def test_missing_exchange_fails_before_report(self):
        with TemporaryDirectory() as temp:
            path=Path(temp)/"report.md"
            good=synthetic([100]*800)
            def unavailable(_):
                raise lab.MarketDataError("Offline public feed")
            with self.assertRaises(lab.MarketDataError):
                lab.run(path,feeds={"Binance":lambda _:good,"Hyperliquid":unavailable})
            self.assertFalse(path.exists())

    def test_report_is_research_only(self):
        with TemporaryDirectory() as temp:
            bars=synthetic([100]*800)
            p=Path(temp)/"research"/"REPORT.md"
            lab.run(p,feeds={"Binance":lambda _:bars,"Hyperliquid":lambda _:bars})
            txt=p.read_text()
            self.assertIn("NO",txt.upper())
            self.assertIn("breakout",txt)
            self.assertIn("pullback",txt)
            self.assertFalse((Path(temp)/"ledger").exists())


if __name__=="__main__":
    unittest.main()
