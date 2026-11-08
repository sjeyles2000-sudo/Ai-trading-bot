"""Unit tests: no network or trading credentials."""
import unittest
from ntfy_paper_alerts import new_events, validate_topic, message

def entry(side="BUY"):
    return {"time_utc":"2026-11-08T01:00:00Z","market":"Binance BTC/USDT spot",
            "side":side,"quantity_btc":"0.002","virtual_price_usd":"100000",
            "virtual_fee_usd":"0.20","virtual_equity_usd":"9999"}

class NtfyTests(unittest.TestCase):
    def test_no_duplicates(self):
        old=[entry()]
        self.assertEqual(new_events(old,old),[])
        self.assertEqual(new_events(old,old+[entry("STOP SELL")])[0]["side"],"STOP SELL")
    def test_reject_truncation(self):
        with self.assertRaises(ValueError):
            new_events([entry()],[])
    def test_url_validation(self):
        validate_topic("https://ntfy.sh/" + "b"*32)
        for value in ("http://ntfy.sh/"+"a"*32,"https://evil.com/"+"a"*32,
                      "https://ntfy.sh/public","https://ntfy.sh/"+"a"*32+"?x=1"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_topic(value)
    def test_brisbane_time(self):
        direction, body = message(entry())
        self.assertEqual(direction, 'BUY')
        self.assertIn('11:00 AM AEST', body)
        self.assertIn('NOT A LIVE TRADE', body)
