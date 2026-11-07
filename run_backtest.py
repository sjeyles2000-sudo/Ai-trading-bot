"""Generate stand-alone historical research reports; never update paper ledger."""
import sys
import time
from pathlib import Path

from bot import fetch_binance, fetch_hyperliquid, MarketDataError
from backtesting import walk_forward, save_report

FEEDS = (("binance","Binance BTC/USDT spot",fetch_binance),
         ("hyperliquid","Hyperliquid BTC perpetual",fetch_hyperliquid))


def run(output_dir=Path("backtest-results"), now_ms=None, feeds=FEEDS):
    now_ms=int(time.time()*1000) if now_ms is None else now_ms
    # Fetch and compute both before writing files, so failed data is not reported
    # as successful. Results are never used to trigger any simulated/live order.
    results={}
    for key,title,fetch in feeds:
        candles=fetch(now_ms)
        results[key]=(title,walk_forward(candles,5,20))
    output_dir=Path(output_dir)
    output_dir.mkdir(parents=True,exist_ok=True)
    for key,(title,result) in results.items():
        save_report(output_dir/(key+".md"),result,title)
        print(f"{title}: holdout return {result['out_of_sample']['return_pct']:+.3f}% "
              f"on {result['out_of_sample']['closed_trades']} closed hypothetical trades")
    print("HISTORICAL RESEARCH ONLY. No orders or paper state modified.")
    return results


if __name__=="__main__":
    try:
        run(Path(sys.argv[1]) if len(sys.argv)==2 else Path("backtest-results"))
    except (OSError,ValueError,MarketDataError) as exc:
        print(f"BACKTEST REPORT NOT COMPLETED: {exc}",file=sys.stderr)
        raise SystemExit(1)
