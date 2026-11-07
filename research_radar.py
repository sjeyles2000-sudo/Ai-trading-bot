"""Read-only research alerts: 5m FOMO/scalping, watched wallet fills, meme candidates.

No account credentials, private keys, real order endpoints, or buy transactions.
Signals are informational only, not verified forecasts or automatic trades.
"""
import json
import math
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlencode

from bot import BINANCE_URL, HYPERLIQUID_URL, MarketDataError, read_json

DEX_BASE = "https://api.dexscreener.com"
FIVE_MIN_MS = 300_000
WALLET_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
MAX_CANDIDATES = 12
MIN_LIQUIDITY_USD = 50_000
MIN_AGE_HOURS = 2
MAX_AGE_HOURS = 72


def finite_number(value, default=0.0):
    try:
        x = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return x if math.isfinite(x) else default


def fomo_signal(prices, volumes):
    """Classify an unusually active SHORT-TERM move; NEVER issue a trade."""
    if len(prices) < 25 or len(volumes) != len(prices):
        raise MarketDataError("Need 25 completed 5m price/volume samples")
    if any(not math.isfinite(p) or p <= 0 for p in prices):
        raise MarketDataError("Invalid scalping prices")
    if any(not math.isfinite(v) or v < 0 for v in volumes):
        raise MarketDataError("Invalid market volumes")
    baseline = sum(volumes[-21:-1]) / 20
    if baseline <= 0:
        return {"signal": "NO_SIGNAL", "reason": "Insufficient trading volume"}
    ratio = volumes[-1] / baseline
    change_15m = 100 * (prices[-1] / prices[-4] - 1)
    momentum = 100 * (prices[-1] / prices[-13] - 1)
    fast = sum(prices[-5:]) / 5
    slow = sum(prices[-20:]) / 20
    # Flag FOMO without turning it into a buy recommendation.
    if ratio >= 3 and change_15m >= 3:
        signal = "FOMO_RISK"
    elif ratio >= 1.8 and change_15m >= 0.7 and fast > slow:
        signal = "BULLISH_WATCH"
    elif ratio >= 1.8 and change_15m <= -0.7 and fast < slow:
        signal = "BEARISH_WATCH"
    else:
        signal = "NO_SIGNAL"
    return {"signal": signal, "volume_ratio": round(ratio, 2),
            "change_15m_pct": round(change_15m, 2),
            "change_60m_pct": round(momentum, 2),
            "last_price": round(prices[-1], 8)}


def read_binance_5m(now_ms):
    params = urlencode({"symbol": "BTCUSDT", "interval": "5m", "limit": 35})
    raw = read_json(f"{BINANCE_URL}?{params}")
    if not isinstance(raw, list):
        raise MarketDataError("Unexpected 5m candles")
    samples = []
    for row in raw:
        try:
            end_ms = int(row[6])
            close = float(row[4])
            volume = float(row[5])
        except (TypeError, IndexError, ValueError) as exc:
            raise MarketDataError("Malformed 5m market data") from exc
        if end_ms <= now_ms:
            samples.append((end_ms, close, volume))
    if len(samples) < 25 or now_ms - samples[-1][0] > 15 * 60_000:
        raise MarketDataError("Insufficient fresh completed 5m candles")
    if len(set(x[0] for x in samples)) != len(samples) or any(
            b[0] - a[0] > FIVE_MIN_MS + 2000 for a, b in zip(samples, samples[1:])):
        raise MarketDataError("Missing or duplicate 5m candles")
    return fomo_signal([x[1] for x in samples], [x[2] for x in samples])


def read_hyperliquid_5m(now_ms):
    raw = read_json(HYPERLIQUID_URL, {
        "type": "candleSnapshot", "req": {"coin": "BTC", "interval": "5m",
        "startTime": now_ms - 36 * FIVE_MIN_MS, "endTime": now_ms}})
    if not isinstance(raw, list):
        raise MarketDataError("Unexpected Hyperliquid 5m candles")
    samples = []
    for row in raw:
        try:
            end_ms = int(row["T"])
            close = float(row["c"])
            volume = float(row["v"])
        except (TypeError, KeyError, ValueError) as exc:
            raise MarketDataError("Malformed Hyperliquid 5m candles") from exc
        if end_ms <= now_ms:
            samples.append((end_ms, close, volume))
    if len(samples) < 25 or now_ms - samples[-1][0] > 15 * 60_000:
        raise MarketDataError("Insufficient fresh completed Hyperliquid 5m candles")
    if len(set(x[0] for x in samples)) != len(samples) or any(
            b[0] - a[0] > FIVE_MIN_MS + 2000 for a, b in zip(samples, samples[1:])):
        raise MarketDataError("Missing or duplicate 5m candles")
    return fomo_signal([x[1] for x in samples], [x[2] for x in samples])


def wallet_fills(addresses, now_ms):
    """Public Hyperliquid fills for explicitly configured wallets only."""
    rows = []
    for address in addresses[:10]:
        if not WALLET_RE.fullmatch(address):
            raise MarketDataError("Invalid wallet address in watchlist")
        fills = read_json(HYPERLIQUID_URL, {"type": "userFills", "user": address})
        if not isinstance(fills, list):
            raise MarketDataError("Unexpected public wallet fills")
        for fill in fills:
            try:
                when = int(fill["time"])
                coin = str(fill["coin"])[:24]
                side = str(fill["dir"])[:40]
                price = finite_number(fill.get("px"))
                size = finite_number(fill.get("sz"))
            except (TypeError, KeyError, ValueError):
                continue
            if now_ms - 24 * 3_600_000 <= when <= now_ms and price > 0 and size > 0:
                rows.append({"wallet": address, "time_ms": when,
                             "market": coin, "direction": side,
                             "price": price, "size": size})
    rows.sort(key=lambda x: x["time_ms"], reverse=True)
    return rows[:30]


def candidates_from_profiles(profiles, now_ms, lookup):
    """Cautious research watchlist, NOT verified new listings or safe tokens."""
    candidates = []
    seen = set()
    for item in profiles[:40]:
        if not isinstance(item, dict):
            continue
        chain, address = item.get("chainId"), item.get("tokenAddress")
        if not isinstance(chain, str) or not isinstance(address, str):
            continue
        if (chain, address) in seen or chain not in ("solana", "base", "ethereum", "bsc"):
            continue
        seen.add((chain, address))
        pairs = lookup(chain, address)
        if not isinstance(pairs, list):
            continue
        valid = [p for p in pairs if isinstance(p, dict)
                 and str(p.get("baseToken", {}).get("address", "")).lower() == address.lower()]
        if not valid:
            continue
        pair = max(valid, key=lambda x: finite_number((x.get("liquidity") or {}).get("usd")))
        liquidity = finite_number((pair.get("liquidity") or {}).get("usd"))
        creation = finite_number(pair.get("pairCreatedAt"))
        age_hours = (now_ms - creation) / 3_600_000 if creation > 0 else -1
        volume = finite_number((pair.get("volume") or {}).get("h24"))
        if liquidity < MIN_LIQUIDITY_USD or not MIN_AGE_HOURS <= age_hours <= MAX_AGE_HOURS:
            continue
        if volume < 10_000:
            continue
        symbol = str((pair.get("baseToken") or {}).get("symbol", "?"))[:20]
        candidates.append({"chain": chain, "symbol": symbol, "address": address,
                           "age_hours": round(age_hours, 1),
                           "liquidity_usd": round(liquidity),
                           "volume_24h_usd": round(volume),
                           "price_usd": finite_number(pair.get("priceUsd")),
                           "url": str(pair.get("url") or "")})
        if len(candidates) >= MAX_CANDIDATES:
            break
    return candidates


def get_meme_candidates(now_ms):
    profiles = read_json(f"{DEX_BASE}/token-profiles/latest/v1")
    if not isinstance(profiles, list):
        raise MarketDataError("Unexpected token profiles")
    def lookup(chain, address):
        # Restrict path components to URL-safe encoding, do not follow profile URLs.
        return read_json(f"{DEX_BASE}/tokens/v1/{quote(chain, safe='')}/{quote(address, safe='')}")
    return candidates_from_profiles(profiles, now_ms, lookup)


def create_report(now_ms, signals, candidates, watched, errors):
    updated = datetime.fromtimestamp(now_ms / 1000, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = ["# Crypto research radar", "", f"Updated {updated}", "",
             "**RESEARCH ONLY — NO REAL TRADES OR AUTOMATIC MEME-COIN BUYS.**",
             "Signals are alerts, not predictions; a high FOMO score can mean extreme downside risk.",
             "", "## 5-minute momentum and FOMO alerts", "",
             "| Market | Alert | 15m move | Relative 5m volume | Last quote |",
             "|---|---|---:|---:|---:|"]
    for name, s in signals.items():
        lines.append(f"| {name} | {s['signal']} | {s.get('change_15m_pct', 0):+.2f}% | {s.get('volume_ratio', 0):.2f}x | ${s.get('last_price', 0):,.2f} |")
    lines += ["", "## Recently profiled token research candidates", "",
              "Recently profiled does not mean newly launched; these may be paid profiles.",
              "Minimum preliminary filters: ≥ $50k reported liquidity; 2–72h pair age; ≥ $10k reported daily volume.",
              "**Not checked:** honeypots, mint/freeze authority, ownership concentration, LP locks, wash trading, audits, taxes, or rugs.",
              "No position sizing or buy action is authorized for these tokens.", "",
              "| Chain | Symbol | Pair age | Liquidity (USD) | 24h volume (USD) | Address |",
              "|---|---|---:|---:|---:|---|"]
    for t in candidates:
        lines.append(f"| {t['chain']} | {t['symbol'].replace('|', '')} | {t['age_hours']:.1f}h | ${t['liquidity_usd']:,} | ${t['volume_24h_usd']:,} | `{t['address']}` |")
    if not candidates:
        lines.append("| — | No candidates passing preliminary filters | — | — | — | — |")
    lines += ["", "## Watched Hyperliquid wallets", "",
              "Only manually added public addresses are monitored; **not** a verified ranking of top traders.",
              "Recent public fills can be delayed or incomplete; copy trading is NOT enabled.", "",
              "| UTC | Wallet | Coin | Direction | Price | Size |",
              "|---|---|---|---|---:|---:|"]
    for w in watched:
        when = datetime.fromtimestamp(w["time_ms"]/1000, timezone.utc).strftime("%m-%d %H:%M")
        lines.append(f"| {when} | `{w['wallet'][:10]}…` | {w['market']} | {w['direction']} | ${w['price']:,.4f} | {w['size']:.4f} |")
    if not watched:
        lines.append("| — | No wallets configured or no recent fills | — | — | — | — |")
    if errors:
        lines.extend(["", "## Feed errors", ""])
        lines.extend(f"- {key}: {val}" for key, val in errors.items())
    lines.extend(["", "Research flags require human review; no real positions are created.",
                  "Public APIs: Binance, Hyperliquid, DEX Screener."])
    return "\n".join(lines) + "\n"


def main(root=Path("."), now_ms=None):
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    root = Path(root)
    errors, signals = {}, {}
    for name, fn in (("Binance BTC spot", read_binance_5m),
                     ("Hyperliquid BTC perpetual", read_hyperliquid_5m)):
        try:
            signals[name] = fn(now_ms)
        except MarketDataError as exc:
            errors[name] = str(exc)
    try:
        candidates = get_meme_candidates(now_ms)
    except MarketDataError as exc:
        candidates = []
        errors["token discovery"] = str(exc)
    addresses = []
    address_file = root / "config" / "wallet_watchlist.json"
    if address_file.exists():
        config = json.loads(address_file.read_text(encoding="utf-8"))
        if not isinstance(config, list) or len(config) > 10 or not all(
                isinstance(a, str) and WALLET_RE.fullmatch(a) for a in config):
            raise MarketDataError("Wallet watchlist must contain at most 10 valid addresses")
        addresses = config
    try:
        watched = wallet_fills(addresses, now_ms)
    except MarketDataError as exc:
        watched = []
        errors["public wallet fills"] = str(exc)
    report = create_report(now_ms, signals, candidates, watched, errors)
    print(report)
    report_path = root / "research" / "RADAR.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    # Each alert stands on its own; do not claim all feeds are healthy if one fails.
    return 0 if not errors else 1


if __name__ == "__main__":
    import sys
    sys.exit(main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")))
