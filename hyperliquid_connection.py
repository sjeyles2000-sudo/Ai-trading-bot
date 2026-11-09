"""Read-only Hyperliquid connection preparation. NEVER signs or submits orders.

No real-trading pathway is implemented. Importing this module is safe.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

MAINNET_INFO_URL = "https://api.hyperliquid.xyz/info"
TESTNET_INFO_URL = "https://api.hyperliquid-testnet.xyz/info"
ADDRESS = re.compile(r"^0x[a-fA-F0-9]{40}$")
LIVE_ORDERS_ENABLED = False  # Non-configurable hard stop. Do not replace with an env toggle.


class ConnectionConfigurationError(ValueError):
    """A public address or environment selection is invalid."""


class LiveTradingDisabled(RuntimeError):
    """No order execution is implemented or permitted."""


@dataclass(frozen=True)
class PublicConnectionConfig:
    """Only public information is represented in this object."""

    network: str
    account_address: str

    @property
    def info_url(self) -> str:
        return TESTNET_INFO_URL if self.network == "testnet" else MAINNET_INFO_URL


def load_public_config(environ=None) -> PublicConnectionConfig:
    """Read *public* account address; never load or print signing credentials.

    An API wallet's address may differ from the master trading account address.
    Set HYPERLIQUID_ACCOUNT_ADDRESS to the master account being inspected.
    """
    env = os.environ if environ is None else environ
    network = env.get("HYPERLIQUID_NETWORK", "testnet").strip().lower()
    if network not in ("testnet", "mainnet"):
        raise ConnectionConfigurationError("Network must be testnet or mainnet")
    address = env.get("HYPERLIQUID_ACCOUNT_ADDRESS", "").strip()
    if not ADDRESS.fullmatch(address):
        raise ConnectionConfigurationError("HYPERLIQUID_ACCOUNT_ADDRESS must be a 0x-prefixed 40-hex-character public address")
    return PublicConnectionConfig(network=network, account_address=address)


def fetch_public_account_state(config: PublicConnectionConfig, *, timeout: float = 10):
    """Retrieve publicly available clearinghouse account state without any API key."""
    payload = json.dumps({"type": "clearinghouseState", "user": config.account_address}).encode("utf-8")
    request = Request(
        config.info_url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "ai-trading-bot-read-only/1.0",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            result = json.load(response)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        raise RuntimeError("Hyperliquid public account query failed") from exc
    if not isinstance(result, dict) or "marginSummary" not in result:
        raise RuntimeError("Unexpected Hyperliquid account response")
    return result


def submit_order(*_args, **_kwargs):
    """Permanent safeguard: no live or testnet order submission is supported."""
    raise LiveTradingDisabled("Order execution is not implemented. Approval and a separate reviewed implementation are required.")


def cancel_order(*_args, **_kwargs):
    """Permanent safeguard: no authenticated order operation is supported."""
    raise LiveTradingDisabled("Authenticated order operations are not implemented.")


if __name__ == "__main__":
    # Safe diagnostics: intentionally no state, balance, private keys or wallet ID in stdout.
    configuration = load_public_config()
    fetch_public_account_state(configuration)
    print(f"Read-only Hyperliquid {configuration.network} connectivity OK; LIVE ORDERS DISABLED")
