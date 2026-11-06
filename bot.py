DEMO_MODE = True
STARTING_BALANCE = 10000.0
MARKETS = ["Binance", "Hyperliquid"]
MAX_TRADE_PERCENT = 0.02


def run_demo():
    print("DEMO MODE ONLY - NO REAL TRADES")
    for market in MARKETS:
        balance = STARTING_BALANCE
        max_trade = balance * MAX_TRADE_PERCENT
        print(f"{market}: starting virtual balance ${balance:.2f}")
        print(f"Maximum simulated trade: ${max_trade:.2f}")
        print("Exchange connection: disabled")
        print("Real orders: disabled")


if __name__ == "__main__":
    run_demo()
