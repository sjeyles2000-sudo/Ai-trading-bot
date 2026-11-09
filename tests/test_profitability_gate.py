"""Offline tests for conservative, no-trade profitability research gate."""
import unittest
from profitability_gate import screen


def report(ret=1.0, dd=0.4, closed=50, pf=1.5):
    return {"return_pct": ret, "max_dd_pct": dd, "closed": closed,
            "profit_factor": pf}


class ProfitabilityGateTests(unittest.TestCase):
    def test_negative_return_is_rejected_even_with_high_win_proxy(self):
        r=screen(report(ret=-0.01,pf=4), report(ret=-0.05), -0.03)
        self.assertEqual(r["decision"], "REJECT")
        self.assertFalse(r["permits_real_trading"])

    def test_double_cost_and_trade_count_gates(self):
        r=screen(report(ret=1,closed=5), report(ret=-0.1), 0)
        self.assertEqual(r["decision"], "REJECT")
        self.assertTrue(any("Too few" in x for x in r["reasons"]))
        self.assertTrue(any("doubled-cost" in x for x in r["reasons"]))

    def test_profit_factor_drawdown_and_benchmark(self):
        r=screen(report(ret=.4,dd=3,pf=1.1), report(ret=.2), .5)
        self.assertEqual(r["decision"], "REJECT")
        self.assertGreaterEqual(len(r["reasons"]), 3)

    def test_pass_is_research_only_not_trade_approval(self):
        r=screen(report(),report(ret=.5),0)
        self.assertEqual(r["decision"], "MORE_RESEARCH_ONLY")
        self.assertTrue(r["requires_unseen_forward_paper_data"])
        self.assertFalse(r["permits_real_trading"])

    def test_missing_and_nonfinite_metrics_fail_closed(self):
        for bad in (dict(report(),return_pct=float("nan")),
                    dict(report(),closed=True),
                    dict(report(),max_dd_pct=float("inf"))):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    screen(bad,report(),0)
        with self.assertRaises(ValueError):
            screen(report(),report(),float("nan"))

if __name__=="__main__":
    unittest.main()
