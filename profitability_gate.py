"""Conservative historical research screen; NEVER authorizes trading.

Passing the screen means only that a historical sample deserves more research.
Requires independent future observations; no account or order access here.
"""
import math

MIN_TRADES = 30
MIN_PROFIT_FACTOR = 1.2
MAX_SAMPLED_DRAWDOWN_PCT = 2.0


def _check_report(name, report):
    if not isinstance(report, dict):
        raise ValueError("Missing " + name + " report")
    for key in ("return_pct", "max_dd_pct"):
        value = report.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("Invalid " + name + " " + key)
    if not 0 <= report["max_dd_pct"] <= 100:
        raise ValueError("Invalid " + name + " drawdown")
    count = report.get("closed")
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ValueError("Invalid " + name + " closed trades")


def screen(holdout, doubled_cost, benchmark_return_pct):
    """Compare net out-of-sample results, modeled cost stress and benchmark.

    No automated promotion or trade signal is generated; forward-paper testing
    and realistic execution analysis are mandatory whatever the result.
    """
    _check_report("holdout", holdout)
    _check_report("doubled_cost", doubled_cost)
    if (isinstance(benchmark_return_pct, bool) or
            not isinstance(benchmark_return_pct, (int, float)) or
            not math.isfinite(benchmark_return_pct)):
        raise ValueError("Invalid benchmark")
    pf = holdout.get("profit_factor")
    if pf is not None and (isinstance(pf, bool) or
                           not isinstance(pf, (int, float)) or
                           not math.isfinite(pf) or pf < 0):
        raise ValueError("Invalid profit factor")
    reasons = []
    if holdout["return_pct"] <= 0:
        reasons.append("Negative or zero net holdout return")
    if doubled_cost["return_pct"] <= 0:
        reasons.append("Negative or zero doubled-cost holdout return")
    if holdout["closed"] < MIN_TRADES:
        reasons.append("Too few completed holdout trades (<30)")
    if pf is None or pf < MIN_PROFIT_FACTOR:
        reasons.append("Profit factor unavailable or below 1.20")
    if holdout["max_dd_pct"] > MAX_SAMPLED_DRAWDOWN_PCT:
        reasons.append("Sampled drawdown above 2%")
    if holdout["return_pct"] <= benchmark_return_pct:
        reasons.append("Fails to beat 2%-allocation BTC benchmark")
    return {
        "decision": "REJECT" if reasons else "MORE_RESEARCH_ONLY",
        "reasons": reasons,
        "requires_unseen_forward_paper_data": True,
        "permits_real_trading": False,
    }
