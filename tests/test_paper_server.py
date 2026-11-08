"""Offline tests of independent server safety; never contact exchanges."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, mock

from server import paper_worker as worker


class PaperServerTests(TestCase):
    def setUp(self):
        self.directory=TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self._state=worker.STATE_DIR
        self._stop=worker.STOP
        worker.STATE_DIR=Path(self.directory.name)
        worker.STOP=False
        self.addCleanup(self._restore)

    def _restore(self):
        worker.STATE_DIR=self._state
        worker.STOP=self._stop

    def test_rejects_any_live_mode_or_secret(self):
        with mock.patch.dict("os.environ",{"TRADING_MODE":"live"}):
            with self.assertRaises(RuntimeError):
                worker.safety()
        with mock.patch.dict("os.environ",{"TRADING_MODE":"paper","ENABLE_LIVE_TRADING":"true"}):
            with self.assertRaises(RuntimeError):
                worker.safety()
        with mock.patch.dict("os.environ",{"TRADING_MODE":"paper","BINANCE_API_SECRET":"dummy"}):
            with self.assertRaises(RuntimeError):
                worker.safety()

    def test_volume_must_be_explicitly_initialized(self):
        with self.assertRaises(RuntimeError):
            worker.verify_volume()
        worker.initialize()
        self.assertTrue((worker.STATE_DIR/".paper-initialized").is_file())
        with self.assertRaises(RuntimeError):
            worker.initialize()
        self.assertFalse((worker.STATE_DIR/"ledger"/"state.json").exists())

    def test_existing_partial_ledger_halts(self):
        worker.initialize()
        (worker.STATE_DIR/"ledger").mkdir()
        with self.assertRaises(RuntimeError):
            worker.verify_volume()

    def test_worker_once_does_not_trade_and_records_status(self):
        worker.initialize()
        runs=[]
        with mock.patch.object(worker.signal,"signal"):
            code=worker.main(["--once"],runner=lambda p:runs.append(p))
        self.assertEqual(code,0)
        self.assertEqual(runs,[worker.STATE_DIR])
        status=json.loads((worker.STATE_DIR/"worker-status.json").read_text())
        self.assertEqual(status["mode"],"paper")
        self.assertEqual(status["status"],"stopped")

    def test_failed_feed_keeps_error_not_fabricated_success(self):
        worker.initialize()
        def broken(_):
            raise worker.MarketDataError("No public candles")
        outcomes=[]
        original=worker.status
        def collect(kind, info):
            outcomes.append(kind)
            original(kind,info)
        with mock.patch.object(worker,"status",side_effect=collect),mock.patch.object(worker.signal,"signal"):
            worker.main(["--once"],runner=broken)
        self.assertEqual(outcomes,["running","error","stopped"])
        self.assertFalse((worker.STATE_DIR/"ledger").exists())

    def test_does_not_initialize_nonempty_directory(self):
        (worker.STATE_DIR/"existing.txt").write_text("preserve")
        with self.assertRaises(RuntimeError):
            worker.initialize()


if __name__=="__main__":
    import unittest
    unittest.main()
