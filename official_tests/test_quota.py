from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from official_viewer.quota import (
    DailyQuotaExceeded,
    DailyUsageLedger,
    RuntimeLock,
    RuntimeLockError,
    UsageLedgerError,
    _process_is_running,
)


class DailyUsageLedgerTests(unittest.TestCase):
    def test_reserves_and_persists_counters_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_path = Path(temporary) / "runtime" / "usage.json"
            ledger = DailyUsageLedger(
                state_path,
                place_limit=2,
                panorama_limit=1,
                today=lambda: date(2026, 7, 13),
            )
            first = ledger.reserve("place")
            second = ledger.reserve("place")
            self.assertEqual(first["place_remaining"], 1)
            self.assertEqual(second["place_remaining"], 0)
            with self.assertRaises(DailyQuotaExceeded):
                ledger.reserve("place")

            persisted = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(
                persisted,
                {"day": "2026-07-13", "place_requests": 2, "panorama_requests": 0},
            )

    def test_new_day_resets_budget(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_path = Path(temporary) / "usage.json"
            state_path.write_text(
                '{"day":"2026-07-12","place_requests":99,"panorama_requests":77}',
                encoding="utf-8",
            )
            ledger = DailyUsageLedger(
                state_path,
                place_limit=2,
                panorama_limit=1,
                today=lambda: date(2026, 7, 13),
            )
            snapshot = ledger.snapshot()
            self.assertEqual(snapshot["place_requests"], 0)
            self.assertEqual(snapshot["panorama_requests"], 0)

    def test_corrupt_state_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_path = Path(temporary) / "usage.json"
            state_path.write_text("not-json", encoding="utf-8")
            ledger = DailyUsageLedger(
                state_path,
                place_limit=2,
                panorama_limit=1,
                today=lambda: date(2026, 7, 13),
            )
            with self.assertRaises(UsageLedgerError):
                ledger.reserve("place")

    def test_runtime_lock_prevents_two_processes_using_one_budget_directory(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            lock_path = Path(temporary) / "viewer.lock"
            first = RuntimeLock(lock_path)
            second = RuntimeLock(lock_path)
            first.acquire()
            with self.assertRaises(RuntimeLockError):
                second.acquire()
            first.release()
            second.acquire()
            second.release()

    def test_runtime_lock_recovers_a_lock_owned_by_a_stopped_process(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            lock_path = Path(temporary) / "viewer.lock"
            lock_path.write_text("999999\n", encoding="ascii")
            lock = RuntimeLock(lock_path)
            with patch("official_viewer.quota._process_is_running", return_value=False):
                lock.acquire()
            self.assertTrue(lock_path.exists())
            lock.release()
            self.assertFalse(lock_path.exists())

    def test_runtime_lock_rechecks_a_process_during_shutdown(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            lock_path = Path(temporary) / "viewer.lock"
            lock_path.write_text("999999\n", encoding="ascii")
            lock = RuntimeLock(lock_path)
            with (
                patch(
                    "official_viewer.quota._process_is_running",
                    side_effect=[True, False],
                ),
                patch("official_viewer.quota.time.sleep") as sleep,
            ):
                lock.acquire()
            sleep.assert_called_once_with(0.1)
            lock.release()

    @unittest.skipUnless(os.name == "nt", "Windows-specific process behavior")
    def test_windows_terminated_process_is_not_treated_as_running(self) -> None:
        process = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
        )
        try:
            self.assertTrue(_process_is_running(process.pid))
            process.terminate()
            process.wait(timeout=5)
            self.assertFalse(_process_is_running(process.pid))
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
