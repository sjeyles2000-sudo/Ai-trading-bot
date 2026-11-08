"""Send best-effort notifications for new *paper* ledger events only.

No trading APIs, account credentials or live order paths.
"""
import csv
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

FIELDS = ("time_utc", "market", "side", "quantity_btc", "virtual_price_usd",
          "virtual_fee_usd", "virtual_equity_usd")
ACTIONS = {"BUY", "SIGNAL SELL", "STOP SELL", "DAILY LIMIT SELL"}
TOPIC = re.compile(r"^/[A-Za-z0-9_-]{24,128}$")


def rows(path):
    path = Path(path)
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != FIELDS:
            raise ValueError("Unexpected paper ledger columns")
        return list(reader)


def new_events(before, after):
    if len(after) < len(before) or after[:len(before)] != before:
        raise ValueError("Paper ledger changed unexpectedly; no notifications")
    return [r for r in after[len(before):] if r["side"] in ACTIONS]


def validate_topic(url):
    parsed = urlparse(url)
    if (parsed.scheme != "https" or parsed.hostname != "ntfy.sh"
            or parsed.port is not None or parsed.username is not None
            or parsed.password is not None or parsed.query or parsed.fragment
            or not TOPIC.fullmatch(parsed.path)):
        raise ValueError("NTFY_TOPIC_URL must be https://ntfy.sh/<unguessable-24+-character-topic>")
    return url


def message(row):
    when = datetime.strptime(row["time_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo("Australia/Brisbane"))
    qty = float(row["quantity_btc"])
    price = float(row["virtual_price_usd"])
    if not 0 < qty < 1e9 or not 0 < price < 1e9:
        raise ValueError("Invalid paper trade")
    direction = "BUY" if row["side"] == "BUY" else "SELL"
    body = (
        f"PAPER {direction} | {row['market']}\n"
        f"Action: {row['side']}\n"
        f"Price: USD {price:,.2f} | Qty: {qty:.8f} BTC\n"
        f"Brisbane: {when:%d %b %Y, %I:%M %p} AEST\n"
        "PAPER SIGNAL ONLY - NOT A LIVE TRADE.\n"
        "https://github.com/sjeyles2000-sudo/Ai-trading-bot/blob/paper-results/ledger/REPORT.md"
    )
    return direction, body


def send(topic, row):
    direction, body = message(row)
    request = Request(topic, data=body.encode("utf-8"), method="POST",
                      headers={"Title": f"AI Trader PAPER {direction}",
                               "Priority": "default", "Tags": "chart_with_upwards_trend"})
    with urlopen(request, timeout=8) as response:
        if response.status // 100 != 2:
            raise OSError("ntfy did not accept the message")


def main():
    if len(sys.argv) != 3:
        raise SystemExit("Usage: ntfy_paper_alerts.py BEFORE_CSV AFTER_CSV")
    before, after = rows(sys.argv[1]), rows(sys.argv[2])
    events = new_events(before, after)
    if not events:
        print("No new paper trade alerts")
        return
    topic = os.environ.get("NTFY_TOPIC_URL", "")
    if not topic:
        print("ntfy not configured; skipped alerts")
        return
    try:
        validate_topic(topic)
    except ValueError as exc:
        print(f"ntfy configuration rejected: {exc}", file=sys.stderr)
        return
    for event in events:
        try:
            send(topic, event)
            print("Sent one paper notification (no order)")
        except (OSError, ValueError) as exc:
            print(f"Notification skipped due to delivery/data error: {type(exc).__name__}",
                  file=sys.stderr)


if __name__ == "__main__":
    main()
