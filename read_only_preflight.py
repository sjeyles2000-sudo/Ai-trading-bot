"""Paper-only architecture preflight. NO AUTHENTICATED API OR ORDER SUBMISSION.
Public prices only; real execution is intentionally unimplemented.
"""
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from bot import BINANCE_URL, HYPERLIQUID_URL, read_json, MarketDataError

# No environment variable, CLI flag, or config can enable execution here.
LIVE_ORDERS_SUPPORTED = False
REAL_LEVERAGE_SUPPORTED = False
RISK_DEFAULTS = {"max_position_fraction":0.02, "max_daily_loss_fraction":0.01,
                 "max_simulated_leverage":2.0, "stop_distance_fraction":0.02}
VENUES = {"binance_spot":{"instrument":"BTCUSDT","mode":"public-read-only"},
          "hyperliquid_spot":{"instrument":"BTC","mode":"research-only"},
          "hyperliquid_perp":{"instrument":"BTC","mode":"simulated-leverage-only"}}


class BlockedOrder(RuntimeError):
    pass


def reject_real_order(*_args, **_kwargs):
    """Permanent fail-closed placeholder; no network or signing code."""
    raise BlockedOrder("REAL ORDERS DISABLED: no exchange order API is implemented")


def check_risk_request(request):
    """Validate requested virtual exposure. No order side effects."""
    if not isinstance(request,dict):
        raise ValueError("Expected simulated request")
    if request.get("mode") != "paper" or request.get("venue") not in VENUES:
        raise BlockedOrder("Only supported PAPER venues permitted")
    if request.get("symbol") != VENUES[request["venue"]]["instrument"]:
        raise BlockedOrder("Symbol not allowlisted")
    if request.get("side") not in ("buy","sell"):
        raise BlockedOrder("Side not allowlisted")
    for name in ("equity_usd","notional_usd","leverage","realized_loss_today_usd"):
        val=request.get(name)
        if isinstance(val,bool) or not isinstance(val,(float,int)) or not math.isfinite(val):
            raise BlockedOrder("Invalid virtual risk input: "+name)
    equity=request["equity_usd"]
    notional=request["notional_usd"]
    leverage=request["leverage"]
    loss=request["realized_loss_today_usd"]
    if equity<=0 or notional<=0 or loss<0:
        raise BlockedOrder("Invalid balances or virtual exposure")
    if loss >= equity*RISK_DEFAULTS["max_daily_loss_fraction"]:
        raise BlockedOrder("Virtual daily-loss halt")
    if notional > equity*RISK_DEFAULTS["max_position_fraction"] + 1e-8:
        raise BlockedOrder("Virtual notional size limit exceeded")
    if request["venue"] == "hyperliquid_perp":
        if not 1 <= leverage <= RISK_DEFAULTS["max_simulated_leverage"]:
            raise BlockedOrder("Virtual leverage limit exceeded")
    elif leverage != 1:
        raise BlockedOrder("Leverage forbidden on spot")
    # Australian derivatives eligibility is NOT inferred from public price feeds.
    return {"approved_for":"hypothetical research only","mode":"paper",
            "venue":request["venue"],"notional_usd":notional,
            "leverage":leverage,"real_order_allowed":False}


def public_snapshot(reader=read_json):
    """Read ONLY unauthenticated prices; never inspect balances or keys."""
    binance=reader(BINANCE_URL+"?"+urlencode({"symbol":"BTCUSDT","interval":"1h","limit":3}))
    if not isinstance(binance,list) or len(binance)<2:
        raise MarketDataError("Binance public data unavailable")
    try:
        bc=float(binance[-2][4])
    except (TypeError,IndexError,ValueError) as exc:
        raise MarketDataError("Binance price invalid") from exc
    hyper=reader(HYPERLIQUID_URL,{"type":"allMids"})
    if not isinstance(hyper,dict):
        raise MarketDataError("Hyperliquid public data unavailable")
    try:
        hc=float(hyper["BTC"])
    except (TypeError,KeyError,ValueError) as exc:
        raise MarketDataError("Hyperliquid public price invalid") from exc
    if not all(math.isfinite(x) and x>0 for x in (bc,hc)):
        raise MarketDataError("Invalid public prices")
    return {"checked_utc":datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "binance_btc_usdt_last_completed_hour":bc,
            "hyperliquid_btc_public_mid":hc,
            "accounts_connected":False,"real_orders_enabled":False}


def write_status(path=Path("preflight-results/STATUS.json"), reader=read_json):
    data=public_snapshot(reader)
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,indent=2)+"\n",encoding="utf-8")
    return data


if __name__=="__main__":
    try:
        # Public-only status. No account identifiers, keys, or secrets.
        print(json.dumps(write_status(),indent=2))
    except (MarketDataError,ValueError,OSError) as exc:
        print("READ-ONLY PREFLIGHT FAILED: "+str(exc))
        raise SystemExit(1)
