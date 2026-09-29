"""Round 4: a missing or empty snapshot never yields a stuck count of 0."""
import os
import re
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from measure.metrics import measure_event
from report.write import build_report
from tests._helpers import extract_embedded_json, mk_provider
from tests.test_round3 import _write_run

B = datetime(2026, 4, 1, 0, 0, 0, tzinfo=timezone.utc)
KEYS = ("stuck_before", "stuck_after", "stuck_carried", "stuck_by_chip")


def _fleet():
    return ([mk_provider("a%d" % i) for i in range(5)]
            + [mk_provider("s%d" % i, runtime_verified=False, requests_served=77)
               for i in range(3)])


class StuckNullTests(unittest.TestCase):
    def _report(self, snaps, releases=None):
        tmp = tempfile.mkdtemp()
        rel = _write_run(tmp, snaps)
        if releases is not None:
            import json
            with open(rel, "w") as f:
                json.dump(releases, f)
        res = build_report(tmp, rel, os.path.join(tmp, "out"))
        with open(os.path.join(tmp, "out", "index.html")) as f:
            html = f.read()
        with open(os.path.join(tmp, "out", "EVENTS.md")) as f:
            md = f.read()
        return res["events"], html, md

    def _assert_no_zero_text(self, html):
        self.assertNotRegex(html, r"\b0 stuck before")
        self.assertNotRegex(html, r"\b0 after\b")
        self.assertIn("No stuck count: no snapshot with providers", html)
        self.assertNotIn("EV.stuck_before || 0", html)
        data = extract_embedded_json(html)
        for e in data["events"]:
            for k in KEYS:
                self.assertIsNone(e[k])

    def test_empty_window(self):
        snaps = [(B, _fleet()), (B + timedelta(hours=10), _fleet())]
        at = B + timedelta(hours=5)
        m = measure_event([s for s in snaps if False], at)
        for k in KEYS:
            self.assertIsNone(m[k])
        events, html, md = self._report(
            snaps, [{"tag": "v1", "published_at": "2026-04-01T05:00:00Z"}])
        self.assertEqual(len(events), 1)
        for k in KEYS:
            self.assertIsNone(events[0][k])
        self._assert_no_zero_text(html)

    def test_empty_first_snapshot_no_snapshot_before(self):
        snaps = [(B, []), (B + timedelta(minutes=2), _fleet()),
                 (B + timedelta(minutes=4), _fleet())]
        m = measure_event(snaps, B)
        self.assertIsNone(m["stuck_before"])
        self.assertIsNone(m["stuck_carried"])
        self.assertIsNone(m["stuck_by_chip"])
        self.assertEqual(m["stuck_after"], 3)
        events, html, md = self._report(snaps)
        self.assertEqual(len(events), 1)
        for k in ("stuck_before", "stuck_carried", "stuck_by_chip"):
            self.assertIsNone(events[0][k])
        self.assertIn("No stuck count: no snapshot with providers in the 30 minutes before the event.", html)
        self.assertNotRegex(html, r"\b0 stuck before")
        self.assertNotRegex(html, r"\b0 after\b")

    def test_restart_at_empty_last_snapshot(self):
        snaps = [(B + timedelta(minutes=2 * i), _fleet()) for i in range(5)]
        snaps.append((B + timedelta(minutes=10), []))
        at = B + timedelta(minutes=10)
        m = measure_event(snaps, at)
        self.assertEqual(m["stuck_before"], 3)
        self.assertIsNone(m["stuck_after"])
        self.assertIsNone(m["stuck_carried"])
        self.assertIsNone(m["stuck_by_chip"])
        events, html, md = self._report(snaps)
        self.assertEqual(len(events), 1)
        self.assertIsNone(events[0]["stuck_after"])
        self.assertIn("No stuck count: no snapshot with providers in the 3 hours after the event.", html)
        self.assertNotRegex(html, r"\b0 stuck before")
        self.assertNotRegex(html, r"\b0 after\b")

    def test_missing_chip_family_does_not_crash(self):
        a = mk_provider("x1", runtime_verified=False)
        b = mk_provider("x2", runtime_verified=False)
        del b["chip_family"]
        snaps = [(B, [a, b]), (B + timedelta(minutes=60), [a, b])]
        m = measure_event(snaps, B + timedelta(minutes=1))
        self.assertEqual(m["stuck_by_chip"], {"M3": 1, "other": 1})


if __name__ == "__main__":
    unittest.main()
