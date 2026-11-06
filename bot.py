"""Public BTC quotes with local, long-only paper execution. No credentials."""
import argparse
from collections import deque
from dataclasses import dataclass, field
import json
import math
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEMO_MODE = True
STARTING_BALANCE = 10_000.0
MARKETS = ("Binance", "Hyperliquid")
MAX_POSITION_PCT = 0.02
STOP_LOSS_PCT = 0.02
SESSION_LOSS_LIMIT_PCT = 0.01
SHORT_WINDOW = 5
LONG_WINDOW = 20
# Conservative estimates per side; these are not account-specific fee quotes.
FEE_RATES = {"Binance": 0.001, "Hyperliquid": 0.00045}
REQUEST_TIMEOUT = 5


def require_demo():
    # Explicit check works even when Python is run with -O.
    if DEMO_MODE is not True:
        raise RuntimeError("Only DEMO_MODE=True is supported")


def valid_price(value):
    if isinstance(value, bool):
        return False
    try:
        return math.isfinite(float(value)) and float(value) > 0
    except (TypeError, ValueError, OverflowError):
        return False


def fetch_price(market):
    """Fetch a fresh public quote; never reuse a failed poll's last price."""
    require_demo()
    if market == "Binance":
        request = Request("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT")
        key = "price"
    elif market == "Hyperliquid":
        request = Request("https://api.hyperliquid.xyz/info",
                          data=b'{"type":"allMids"}',
                          headers={"Content-Type": "application/json"}, method="POST")
        key = "BTC"
    else:
        raise ValueError(f"Unknown market: {market}")
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            payload = json.load(response)
        price = payload[key]
        if not valid_price(price):
            raise ValueError("Invalid BTC price")
        return float(price)
    except (HTTPError, URLError, OSError, ValueError, TypeError, KeyError) as exc:
        print(f"{market}: market data unavailable ({type(exc).__name__}); skipping")
        return None


@dataclass
class PaperAccount:
    market: str
    cash: float = field(default=STARTING_BALANCE, init=False)
    units: float = field(default=0.0, init=False)
    entry_price: float = field(default=0.0, init=False)
    fees: float = field(default=0.0, init=False)
    trades: int = field(default=0, init=False)
    halted: bool = field(default=False, init=False)
    prices: deque = field(default_factory=lambda: deque(maxlen=LONG_WINDOW), init=False)

    def __post_init__(self):
        require_demo()
        if self.market not in MARKETS:
            raise ValueError("Unsupported market")

    def equity(self, price):
        return self.cash + self.units * price

    def liquidation_equity(self, price):
        return self.cash + self.units * price * (1 - FEE_RATES[self.market])

    def _sell(self, price, reason):
        require_demo()
        proceeds = self.units * price
        fee = proceeds * FEE_RATES[self.market]
        self.cash += proceeds - fee
        self.fees += fee
        self.trades += 1
        print(f"{self.market}: PAPER SELL {self.units:.8f} BTC at ${price:.2f}; "
              f"fee ${fee:.4f}; {reason}")
        self.units = self.entry_price = 0.0
        return "SELL"

    def step(self, price):
        require_demo()
        if not valid_price(price):
            # Rebuild signals after an outage; never fill using a stale quote.
            self.prices.clear()
            return None
        price = float(price)
        self.prices.append(price)
        limit = STARTING_BALANCE * (1 - SESSION_LOSS_LIMIT_PCT)
        if self.liquidation_equity(price) <= limit:
            self.halted = True
        if self.halted:
            return self._sell(price, "session loss halt") if self.units else None
        if self.units and price <= self.entry_price * (1 - STOP_LOSS_PCT):
            action = self._sell(price, "2% stop-loss")
        elif len(self.prices) < LONG_WINDOW:
            return None
        else:
            prices = list(self.prices)
            short_avg = sum(prices[-SHORT_WINDOW:]) / SHORT_WINDOW
            long_avg = sum(prices) / LONG_WINDOW
            if self.units and short_avg < long_avg:
                action = self._sell(price, "moving average signal")
            elif not self.units and short_avg > long_avg:
                rate = FEE_RATES[self.market]
                # Budget includes entry fee; notional is also <=2% after entry fee.
                budget = min(self.cash, self.equity(price) * MAX_POSITION_PCT)
                notional = budget / (1 + rate)
                # Reserve both fees when checking the session loss floor.
                if notional <= 0 or self.cash - 2 * notional * rate <= limit:
                    return None
                fee = notional * rate
                self.units = notional / price
                self.cash -= notional + fee
                self.entry_price = price
                self.fees += fee
                self.trades += 1
                print(f"{self.market}: PAPER BUY {self.units:.8f} BTC at ${price:.2f}; fee ${fee:.4f}")
                return "BUY"
            else:
                return None
        if self.cash <= limit:
            self.halted = True
        return action


def run(steps=120, interval=5.0):
    require_demo()
    if steps < 1 or not math.isfinite(interval) or interval < 0:
        raise ValueError("steps must be positive and interval finite and nonnegative")
    accounts = {market: PaperAccount(market) for market in MARKETS}
    print("DEMO_MODE=True: PUBLIC BTC DATA; SIMULATED ORDERS ONLY")
    for index in range(steps):
        for market, account in accounts.items():
            price = fetch_price(market)
            account.step(price)
            if price is not None:
                print(f"{market}: virtual equity ${account.equity(price):.2f}; "
                      f"estimated fees ${account.fees:.4f}; simulated orders {account.trades}")
        if index + 1 < steps:
            time.sleep(interval)
    return accounts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--steps", type=int, default=120)
    parser.add_argument("--interval", type=float, default=5.0)
    args = parser.parse_args()
    run(args.steps, args.interval)
