"""Offline safety tests; no network or exchange credentials required."""
import unittest
from unittest.mock import patch

from hyperliquid_connection import (
    ConnectionConfigurationError,
    LiveTradingDisabled,
    load_public_config,
    fetch_public_account_state,
    submit_order,
    cancel_order,
    LIVE_ORDERS_ENABLED,
)

WALLET = "0x" + "a" * 40


class HyperliquidSafetyTests(unittest.TestCase):
    def test_paper_first_default(self):
        config = load_public_config({"HYPERLIQUID_ACCOUNT_ADDRESS": WALLET})
        self.assertEqual(config.network, "testnet")
        self.assertIn("testnet", config.info_url)

    def test_explicit_mainnet_is_still_read_only(self):
        config = load_public_config({
            "HYPERLIQUID_NETWORK": "mainnet",
            "HYPERLIQUID_ACCOUNT_ADDRESS": WALLET,
        })
        self.assertEqual(config.network, "mainnet")
        self.assertFalse(LIVE_ORDERS_ENABLED)
        with self.assertRaises(LiveTradingDisabled):
            submit_order(config, "BTC", 1)

    def test_reject_bad_address(self):
        for value in ("", "0x123", "not-a-wallet", "0x" + "z" * 40):
            with self.subTest(value=value):
                with self.assertRaises(ConnectionConfigurationError):
                    load_public_config({"HYPERLIQUID_ACCOUNT_ADDRESS": value})

    def test_reject_bad_network(self):
        with self.assertRaises(ConnectionConfigurationError):
            load_public_config({"HYPERLIQUID_ACCOUNT_ADDRESS": WALLET, "HYPERLIQUID_NETWORK": "unknown"})

    def test_all_order_routes_blocked(self):
        with self.assertRaises(LiveTradingDisabled):
            submit_order()
        with self.assertRaises(LiveTradingDisabled):
            cancel_order()

    def test_public_query_sends_no_credentials(self):
        config = load_public_config({"HYPERLIQUID_ACCOUNT_ADDRESS": WALLET})
        with patch("hyperliquid_connection.urlopen") as mocked:
            mocked.return_value.__enter__.return_value.read.return_value = b'{"marginSummary": {}}'
            fetch_public_account_state(config)
            request = mocked.call_args.args[0]
            self.assertEqual(request.get_method(), "POST")
            self.assertIn(b"clearinghouseState", request.data)
            self.assertNotIn("Authorization", request.headers)
            self.assertNotIn(b"private", request.data)
            self.assertNotIn(b"secret", request.data)


if __name__ == "__main__":
    unittest.main()
