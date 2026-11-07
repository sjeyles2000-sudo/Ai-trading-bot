"""Static security and contract checks for the public read-only monitor."""
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.scripts = []
        self.external_targets = []
    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if "id" in d:
            self.ids.add(d["id"])
        if tag == "script":
            self.scripts.append(d.get("src", ""))
        if tag == "a" and d.get("target") == "_blank":
            self.external_targets.append(d)


class PerformancePanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = (DOCS/"index.html").read_text(encoding="utf-8")
        cls.script = (DOCS/"performance.js").read_text(encoding="utf-8")
        cls.parsed = PageParser()
        cls.parsed.feed(cls.page)

    def test_performance_panel_has_required_dom_elements(self):
        for element in ("performance-panel", "performance-status",
                        "performance-list", "strategy-panel", "strategy-lab-link"):
            self.assertIn(element, self.parsed.ids)

    def test_script_is_local_and_csp_compatible(self):
        self.assertIn("./performance.js", self.parsed.scripts)
        self.assertIn("script-src 'self'", self.page)
        self.assertIn("connect-src", self.page)
        for link in self.parsed.external_targets:
            self.assertIn("noopener", link.get("rel", ""))
            self.assertIn("noreferrer", link.get("rel", ""))

    def test_no_trading_or_wallet_actions_in_new_code(self):
        for forbidden in ("api_key", "private_key", "userFills", "walletConnect",
                          "executeTrade", "placeOrder", "order/submit", "eth_sendTransaction"):
            self.assertNotIn(forbidden.lower(), self.script.lower())
        self.assertIn("paper-results/", self.script)
        self.assertNotIn("POST", self.script)

    def test_snapshot_staleness_and_zero_trades_are_explicit(self):
        self.assertIn("freshHours = 3", self.script)
        self.assertIn("Stale paper snapshot", self.script)
        self.assertIn("Recorded virtual P/L", self.script)
        self.assertIn("simulated transactions", self.script)
        self.assertIn("not a live exchange account", self.script)
        self.assertIn("negative holdout returns", self.page)
        self.assertIn("NOT DEPLOYED", self.page)


if __name__ == "__main__":
    unittest.main()
