"""Failing-first test for report/write.py.

Covers T8: a
replay of build_report against a committed fixture built from the real,
recorded raw data for the 2026-09-28 20:10Z-21:50Z restart window,
asserting the expected event metrics plus the
"coordinator restart" label. The fixture lives under
tests/fixtures/restart_20260928/ so this test carries no dependency on any
path outside the repo and is never skipped.
"""
import json
import os
import re
import tempfile
import unittest
from datetime import datetime, timezone

from report.write import build_report

RAW_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "restart_20260928")
RELEASES_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "releases.json")

_ISO_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})")


def parse_iso_utc(s):
    m = _ISO_RE.match(s)
    if not m:
        raise ValueError("not an ISO UTC timestamp: %r" % (s,))
    y, mo, d, h, mi, se = (int(x) for x in m.groups())
    return datetime(y, mo, d, h, mi, se, tzinfo=timezone.utc)


class BuildReportRealDataReplayTests(unittest.TestCase):
    def test_T8_replay_recorded_restart_and_no_release(self):
        if not os.path.isdir(RAW_DIR):
            self.fail(
                "committed fixture not found at %s -- T8 is a required "
                "replay test against real recorded data and must not be "
                "skipped; the fixture is missing"
                % (RAW_DIR,)
            )
        if not os.path.isfile(RELEASES_PATH):
            self.fail("missing releases fixture at %s" % (RELEASES_PATH,))

        with tempfile.TemporaryDirectory() as out_dir:
            result = build_report(RAW_DIR, RELEASES_PATH, out_dir)

            self.assertIsInstance(result, dict)
            for key in ("events", "skipped_files", "stuck_now"):
                self.assertIn(key, result)

            events_json_path = os.path.join(out_dir, "events.json")
            events_md_path = os.path.join(out_dir, "EVENTS.md")
            self.assertTrue(
                os.path.isfile(events_json_path),
                "build_report must write out_dir/events.json",
            )
            self.assertTrue(
                os.path.isfile(events_md_path),
                "build_report must write out_dir/EVENTS.md",
            )

            with open(events_json_path) as f:
                written_events = json.load(f)
            self.assertEqual(
                written_events, result["events"],
                "events.json on disk must match the returned events list",
            )

        self.assertIsInstance(result["skipped_files"], int)
        self.assertGreaterEqual(result["skipped_files"], 0)

        # --- restart event: 2026-09-28 20:42Z - 20:45Z ---
        window_start = datetime(2026, 9, 28, 20, 42, 0, tzinfo=timezone.utc)
        window_end = datetime(2026, 9, 28, 20, 45, 0, tzinfo=timezone.utc)

        restart_events = [e for e in result["events"] if e.get("kind") == "restart"]
        in_window = [
            e for e in restart_events
            if window_start <= parse_iso_utc(e["at"]) <= window_end
        ]

        self.assertEqual(
            len(in_window), 1,
            "expected exactly one restart event between 20:42Z and 20:45Z "
            "on 2026-09-28, got restart events at: %r"
            % ([e.get("at") for e in restart_events],),
        )

        ev = in_window[0]
        self.assertEqual(
            ev["label"], "coordinator restart",
            "restart events must be labelled 'coordinator restart', not "
            "the bare kind name 'restart'",
        )
        self.assertGreaterEqual(
            ev["drop"], 1100,
            "the coordinator restart on 2026-09-28 should show a drop of "
            "at least 1,100 macs",
        )
        self.assertIsNotNone(
            ev["recovery_minutes"],
            "the fleet recovered within the recorded window, so "
            "recovery_minutes must not be null",
        )
        self.assertLess(ev["recovery_minutes"], 10)
        self.assertGreaterEqual(
            ev["stuck_carried"], 6,
            "at least 6 providers stuck with runtime_verified=false before "
            "the restart must be matched as carried through it",
        )

        # --- no release event: the fixture's span (20:10Z-21:50Z) contains
        # no release publish times from tests/fixtures/releases.json ---
        release_events = [e for e in result["events"] if e.get("kind") == "release"]
        self.assertEqual(
            len(release_events), 0,
            "expected no release events in the fixture's recorded span "
            "(2026-09-28 20:10Z-21:50Z); no release in "
            "tests/fixtures/releases.json falls inside it, got: %r"
            % (release_events,),
        )


if __name__ == "__main__":
    unittest.main()
