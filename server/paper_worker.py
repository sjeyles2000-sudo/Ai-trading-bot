"""Container entrypoint for an independent paper-only hourly worker.

No exchange credentials, order endpoints, authenticated trading, or leverage.
An explicit initialization step is needed once on an attached persistent volume.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import sys
import time
from datetime import datetime, timezone

# Bring the existing, intentionally read-only simulator into the module path.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bot import DEMO_MODE, MarketDataError
from demo_runner import run

STATE_DIR = Path(os.environ.get("PAPER_STATE_DIR", "/data")).resolve()
STOP = False


def utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safety():
    if DEMO_MODE is not True:
        raise RuntimeError("Demo-mode code lock is disabled")
    if os.environ.get("TRADING_MODE", "paper") != "paper":
        raise RuntimeError("Only TRADING_MODE=paper is permitted")
    if os.environ.get("ENABLE_LIVE_TRADING", "").strip().lower() in ("true", "1", "yes"):
        raise RuntimeError("Live trading prohibited")
    for key in ("BINANCE_API_KEY", "BINANCE_API_SECRET", "HYPERLIQUID_PRIVATE_KEY",
                "HYPERLIQUID_AGENT_PRIVATE_KEY", "WALLET_PRIVATE_KEY"):
        if os.environ.get(key):
            raise RuntimeError("Do not provide exchange credentials to paper-only service")
    if not STATE_DIR.is_absolute():
        raise RuntimeError("Use absolute data directory")


def paths():
    return STATE_DIR / ".paper-initialized", STATE_DIR / "ledger" / "state.json"


def initialize():
    safety()
    marker, state = paths()
    if marker.exists():
        raise RuntimeError("Volume already initialized; cannot reset existing virtual balances")
    if any(STATE_DIR.iterdir()) if STATE_DIR.exists() else False:
        raise RuntimeError("Data directory is not empty; refusing initialization")
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    marker.write_text("paper-only volume initialized "+utc()+"\n", encoding="utf-8")
    print("Paper data volume initialized. No real trades.", flush=True)


def verify_volume():
    marker, state = paths()
    if not marker.is_file():
        raise RuntimeError("Uninitialized volume: initialize manually; do not run on ephemeral storage")
    if (STATE_DIR / "ledger").exists() and not state.is_file():
        raise RuntimeError("Ledger exists but state missing: manual reconciliation required")
    return state


def status(kind, info):
    # Machine-readable health only: never log accounts, credentials, or position values.
    msg={"time_utc":utc(),"mode":"paper","status":kind,"detail":str(info)[:200]}
    temp=STATE_DIR / ".worker-status.tmp"
    temp.write_text(json.dumps(msg)+"\n",encoding="utf-8")
    temp.replace(STATE_DIR / "worker-status.json")
    print(json.dumps(msg),flush=True)


def stop_signal(_sig, _frame):
    global STOP
    STOP=True


def main(argv=None, runner=run, sleeper=time.sleep):
    parser=argparse.ArgumentParser()
    parser.add_argument("--initialize",action="store_true",
                        help="One-time manual persistent volume initialization")
    parser.add_argument("--once",action="store_true",help="Run one paper cycle then exit")
    args=parser.parse_args(argv)
    safety()
    if args.initialize:
        initialize()
        return 0
    verify_volume()
    signal.signal(signal.SIGTERM,stop_signal)
    signal.signal(signal.SIGINT,stop_signal)
    lock=(STATE_DIR / ".paper-worker.lock").open("a+")
    try:
        fcntl.flock(lock.fileno(),fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        raise RuntimeError("Another worker is using this virtual ledger") from exc
    status("running","Paper service started; public exchange candles only")
    while not STOP:
        try:
            verify_volume()
            runner(STATE_DIR)
            status("ok","Cycle completed; virtual results only")
        except (MarketDataError,OSError,ValueError) as exc:
            # No fabricated success: failed cycles are shown as errors and retried later.
            status("error",f"{type(exc).__name__}: {exc}")
        if args.once:
            break
        # Hourly runs are sufficient for the current hourly research strategy.
        # Interruptible sleep for graceful shutdown, no low-latency scalping claims.
        for _ in range(3600):
            if STOP:
                break
            sleeper(1)
    status("stopped","No new cycles until restarted")
    return 0


if __name__=="__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError,OSError) as exc:
        print(f"PAPER WORKER REFUSED TO START: {exc}",file=sys.stderr,flush=True)
        raise SystemExit(1)
