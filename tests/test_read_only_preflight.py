"""Deterministic read-only safety boundary tests (no real network)."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from read_only_preflight import (LIVE_ORDERS_SUPPORTED, REAL_LEVERAGE_SUPPORTED,
    BlockedOrder, reject_real_order, check_risk_request, public_snapshot, write_status)

def request(venue="binance_spot",leverage=1,notional=100,loss=0):
    return {"mode":"paper","venue":venue,
            "symbol":"BTCUSDT" if venue=="binance_spot" else "BTC",
            "side":"buy","equity_usd":10000,"notional_usd":notional,
            "leverage":leverage,"realized_loss_today_usd":loss}

class ReadOnlySafetyTests(unittest.TestCase):
    def test_live_is_never_supported(self):
        self.assertFalse(LIVE_ORDERS_SUPPORTED)
        self.assertFalse(REAL_LEVERAGE_SUPPORTED)
        with self.assertRaises(BlockedOrder):
            reject_real_order(venue="binance_spot",live=True)

    def test_valid_virtual_spot_and_perp(self):
        self.assertFalse(check_risk_request(request())["real_order_allowed"])
        self.assertFalse(check_risk_request(request("hyperliquid_perp",2))["real_order_allowed"])

    def test_rejects_live_mode_spot_leverage_and_oversize(self):
        cases=[dict(request(),mode="live"),request("binance_spot",2),
               request("hyperliquid_perp",3),request(notional=201),
               request(loss=100),dict(request(),side="withdraw")]
        for c in cases:
            with self.subTest(c=c),self.assertRaises(BlockedOrder):
                check_risk_request(c)

    def test_readonly_urls_and_no_private_calls(self):
        calls=[]
        def fake(url,payload=None):
            calls.append((url,payload))
            if "binance" in url:
                return [[0,1,1,1,1,1,1],[0,1,1,1,"123.45",1,1],[0,1,1,1,1,1,1]]
            return {"BTC":"123.5"}
        data=public_snapshot(fake)
        self.assertEqual(len(calls),2)
        self.assertIn("/api/v3/klines",calls[0][0])
        self.assertEqual(calls[1][1],{"type":"allMids"})
        self.assertFalse(data["accounts_connected"])
        self.assertFalse(data["real_orders_enabled"])

    def test_failed_feed_never_writes_status(self):
        with TemporaryDirectory() as d:
            path=Path(d)/"STATUS.json"
            def broken(url,payload=None):
                raise ValueError("offline")
            with self.assertRaises(ValueError):
                write_status(path,broken)
            self.assertFalse(path.exists())

if __name__=="__main__":
    unittest.main()
