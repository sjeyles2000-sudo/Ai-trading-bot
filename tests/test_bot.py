import contextlib
import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import bot


class SafetyTests(unittest.TestCase):
    def setUp(self):
        self.output = contextlib.redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def bought(self, market='Binance'):
        account = bot.PaperAccount(market)
        for price in range(100, 120):
            account.step(price)
        self.assertGreater(account.units, 0)
        return account

    def test_starting_balance_and_independent_accounts(self):
        a, b = map(bot.PaperAccount, bot.MARKETS)
        self.assertEqual((a.cash, b.cash), (10000, 10000))
        a.step(100)
        self.assertEqual(len(b.prices), 0)

    def test_position_cap_and_entry_fee_both_markets(self):
        for market in bot.MARKETS:
            a = self.bought(market)
            notional = a.units * a.entry_price
            self.assertLessEqual(notional, .02 * a.equity(a.entry_price))
            self.assertAlmostEqual(a.cash + notional + a.fees, 10000)
            self.assertAlmostEqual(a.fees, notional * bot.FEE_RATES[market])
            units = a.units
            a.step(120)
            self.assertEqual(a.units, units)  # no stacking positions

    def test_stop_loss_at_boundary_includes_exit_fee(self):
        a = self.bought()
        units, cash, fees = a.units, a.cash, a.fees
        price = a.entry_price * .98
        self.assertEqual(a.step(price), 'SELL')
        self.assertEqual(a.units, 0)
        self.assertAlmostEqual(a.cash, cash + units * price * .999)
        self.assertAlmostEqual(a.fees, fees + units * price * .001)

    def test_automatic_signal_sell(self):
        a = self.bought()
        for _ in range(20):
            a.step(118)  # above stop, below short average
            if not a.units:
                break
        self.assertEqual(a.units, 0)
        self.assertEqual(a.trades, 2)

    def test_session_limit_liquidates_and_latches(self):
        a = self.bought()
        # A gap can exceed the limit; execute only at the observed price.
        self.assertEqual(a.step(1), 'SELL')
        self.assertTrue(a.halted)
        for price in range(100, 150):
            a.step(price)
        self.assertEqual(a.trades, 2)
        self.assertEqual(a.units, 0)

    def test_session_boundary_and_fees(self):
        a = bot.PaperAccount('Binance')
        a.cash = 9900
        a.step(100)
        self.assertTrue(a.halted)
        a = self.bought()
        # Liquidation fees push equity to the limit even if gross equity is above.
        price = (9900 - a.cash) / (a.units * .999)
        a.step(price * (1 - 1e-12))
        self.assertTrue(a.halted)

    def test_invalid_data_does_not_trade_or_change_account(self):
        for invalid in (None, 0, -1, float('nan'), float('inf'), 'bad', True, {}):
            a = self.bought()
            state = (a.cash, a.units, a.fees, a.trades)
            self.assertIsNone(a.step(invalid))
            self.assertEqual(state, (a.cash, a.units, a.fees, a.trades))
            self.assertEqual(len(a.prices), 0)
            self.assertEqual(a.step(a.entry_price * .97), 'SELL')

    def test_demo_guard_at_all_execution_boundaries(self):
        a = self.bought()
        with patch.object(bot, 'DEMO_MODE', False), patch.object(bot, 'urlopen') as network:
            for call in (lambda: bot.PaperAccount('Binance'), lambda: a.step(100),
                         lambda: a._sell(100, 'test'), lambda: bot.run(1, 0),
                         lambda: bot.fetch_price('Binance')):
                with self.assertRaises(RuntimeError):
                    call()
            network.assert_not_called()

    def test_public_requests_only(self):
        for market, payload in [('Binance', {'price': '65000'}),
                                ('Hyperliquid', {'BTC': '65001'})]:
            response = io.StringIO(json.dumps(payload))
            with patch.object(bot, 'urlopen') as network:
                network.return_value.__enter__.return_value = response
                self.assertEqual(bot.fetch_price(market), float(next(iter(payload.values()))))
                request = network.call_args.args[0]
                self.assertEqual(network.call_args.kwargs['timeout'], 5)
                self.assertNotIn('Authorization', request.headers)
                if market == 'Binance':
                    self.assertEqual(request.get_method(), 'GET')
                    self.assertEqual(request.full_url, 'https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT')
                else:
                    self.assertEqual(request.full_url, 'https://api.hyperliquid.xyz/info')
                    self.assertEqual(json.loads(request.data), {'type': 'allMids'})

    def test_feed_errors(self):
        errors = [URLError('offline'), TimeoutError(),
                  HTTPError('url', 429, 'rate limit', {}, None)]
        for market in bot.MARKETS:
            for error in errors:
                with patch.object(bot, 'urlopen', side_effect=error):
                    self.assertIsNone(bot.fetch_price(market))
            for payload in ('bad json', '{}', '[]', '{"price":0,"BTC":"NaN"}'):
                with patch.object(bot, 'urlopen') as network:
                    network.return_value.__enter__.return_value = io.StringIO(payload)
                    self.assertIsNone(bot.fetch_price(market))

    def test_demo_run(self):
        # Exercise the actual runner, automatic BUY/SELL and independent feed outage.
        def quote(market):
            i = counters[market]
            counters[market] += 1
            if market == 'Hyperliquid' and i == 0:
                return None
            return 100 + i if i < 22 else 1
        counters = dict.fromkeys(bot.MARKETS, 0)
        with patch.object(bot, 'fetch_price', side_effect=quote), patch.object(bot, 'urlopen') as network:
            accounts = bot.run(24, 0)
            network.assert_not_called()
        for a in accounts.values():
            self.assertEqual(a.trades, 2)
            self.assertTrue(a.halted)
            self.assertEqual(a.units, 0)


if __name__ == '__main__':
    unittest.main()
