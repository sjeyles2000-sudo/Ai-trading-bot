"""Offline Elysium launchpad risk triage. Research only; no trading or network access.

Input is a manually reviewed JSON snapshot with *independently checked* figures.
This tool cannot verify token identity, detect honeypots, or fetch live quotes.
Do not treat a passing screen as an investment recommendation.
"""
import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

MIN_LIQUIDITY_USD = 50000
MIN_DAILY_VOLUME_USD = 25000
MAX_TOP10_HOLDER_PCT = 35
MAX_ROUND_TRIP_COST_PCT = 3.0
MAX_SNAPSHOT_AGE_HOURS = 2
WATCHLIST = ("STOCKIUM", "BOXA", "ASCEND")


def number(data, name):
    value = data.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) and value >= 0 else None


def evaluate(row, now):
    """Return fail-closed classification for one independently verified asset."""
    if not isinstance(row, dict):
        raise ValueError("Each token must be an object")
    name = str(row.get("project", "")).strip()
    if name not in WATCHLIST:
        raise ValueError("Unrecognized project; use STOCKIUM, BOXA or ASCEND")
    reasons = []
    source = row.get("source_url")
    if not isinstance(source, str) or not source.startswith("https://"):
        reasons.append("Missing HTTPS source URL")
    chain = row.get("chain")
    contract = row.get("contract_address")
    if not isinstance(chain, str) or not chain.strip():
        reasons.append("Chain/network not verified")
    if not isinstance(contract, str) or not contract.strip():
        reasons.append("Token contract/address not verified")
    timestamp = row.get("observed_at")
    if not isinstance(timestamp, str):
        reasons.append("Missing timestamp")
    else:
        try:
            observed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            if observed.tzinfo is None:
                raise ValueError("Timezone missing")
            age = (now - observed).total_seconds() / 3600
            if age < -0.05 or age > MAX_SNAPSHOT_AGE_HOURS:
                reasons.append("Stale or future-dated snapshot")
        except ValueError:
            reasons.append("Invalid timestamp")
    checks = (
        ("liquidity_usd", MIN_LIQUIDITY_USD, "below minimum liquidity", False),
        ("volume_24h_usd", MIN_DAILY_VOLUME_USD, "below minimum 24h volume", False),
        ("top10_holder_pct", MAX_TOP10_HOLDER_PCT, "top-10 concentration too high", True),
        ("round_trip_cost_pct", MAX_ROUND_TRIP_COST_PCT, "estimated total trading costs too high", True),
    )
    for field, limit, message, maximum in checks:
        v = number(row, field)
        if v is None:
            reasons.append("Missing or invalid " + field)
        elif (v > limit if maximum else v < limit):
            reasons.append(message)
    if row.get("sell_simulation_verified") is not True:
        reasons.append("Sellability not independently verified")
    if row.get("contract_permissions_reviewed") is not True:
        reasons.append("Contract privileges not reviewed")
    # Research screen only, not approval to buy, even when all checks pass.
    return {"project": name, "status": "RESEARCH SCREEN PASS" if not reasons else "NOT READY",
            "reasons": reasons or ["Screen passed; still NOT investment or execution approval"]}


def build_report(items, now):
    if not isinstance(items, list) or len(items) > 100:
        raise ValueError("Expected JSON array of at most 100 snapshots")
    seen = set()
    lines = ["# Elysium research-only risk screen", "",
             "Generated " + now.isoformat(), "",
             "**NO ORDERS, NO WALLET CONNECTIONS, NO AUTOMATIC TRADES.**",
             "This offline checker does not fetch prices, authenticate projects, or prove profitability.",
             "Manual token contract and independent source verification are essential.", "",
             "| Project | Screen | Reasons |", "|---|---|---|"]
    for item in items:
        result = evaluate(item, now)
        name = result["project"]
        if name in seen:
            raise ValueError("Duplicate project in snapshot")
        seen.add(name)
        reasons = "; ".join(result["reasons"]).replace("|", "/")
        lines.append(f'| {name} | {result["status"]} | {reasons} |')
    for name in WATCHLIST:
        if name not in seen:
            lines.append(f"| {name} | NOT READY | No verified snapshot supplied |")
    lines += ["", "Passing thresholds is NOT a buy signal. Risk of rug pulls, price",
              "manipulation, token taxes, slippage, and total loss remains.",
              "For paper strategy research, separately record entry/exit quotes,",
              "fees, liquidity, impact, order-book depth, and outcomes before conclusions.", ""]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, help="Optional locally reviewed JSON array")
    parser.add_argument("--output", type=Path, default=Path("elysium-risk-report.md"))
    args = parser.parse_args(argv)
    now = datetime.now(timezone.utc)
    rows = json.loads(args.snapshot.read_text(encoding="utf-8")) if args.snapshot else []
    report = build_report(rows, now)
    args.output.write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
