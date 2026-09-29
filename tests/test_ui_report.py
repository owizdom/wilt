"""Failing-first integration tests for build_report's new out/index.html
output.

Covers acceptance tests:
  U3 - build_report writes out_dir/index.html; the embedded JSON parses and
       equals the computed timeline, events (each with "window" and
       "chips_before" merged in) and stuck_now, plus "span".
  U4 - index.html has no http(s) URLs, no <script src, no <link.
  U5 - with zero events, the page is written and contains the no-events
       line.
  U6 - on the committed real-data restart fixture, index.html is under
       500 KB and its embedded events include one at 2026-09-28T20:42:37Z.
"""
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from detect.snapshots import load_stats
from report.timeline import build_timeline, event_window
from report.write import build_report

from tests._helpers import extract_embedded_json, iso_utc, mk_provider, parse_iso_utc, write_json_gz

FIXTURE_RAW_DIR = os.path.join(
    os.path.dirname(__file__), "fixtures", "restart_20260928"
)
FIXTURE_RELEASES_PATH = os.path.join(
    os.path.dirname(__file__), "fixtures", "releases.json"
)


def _write_empty_releases(path):
    with open(path, "w") as f:
        json.dump([], f)


def _build_event_bearing_raw_dir(root):
    """A small raw dir with one restart event and one release event inside
    its recorded span, for U3/U4."""
    raw_dir = os.path.join(root, "raw")
    stats_dir = os.path.join(raw_dir, "stats")
    os.makedirs(stats_dir)

    t0 = datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(minutes=5)   # empty -> restart event at t1
    t2 = t0 + timedelta(minutes=10)
    t3 = t0 + timedelta(hours=1)
    t4 = t0 + timedelta(hours=2)

    write_json_gz(
        os.path.join(stats_dir, "20260301T000000Z.json.gz"),
        {"providers": [mk_provider("p%d" % i) for i in range(20)]},
    )
    write_json_gz(
        os.path.join(stats_dir, "20260301T000500Z.json.gz"),
        {"providers": []},
    )
    write_json_gz(
        os.path.join(stats_dir, "20260301T001000Z.json.gz"),
        {"providers": [mk_provider("new%d" % i) for i in range(20)]},
    )
    write_json_gz(
        os.path.join(stats_dir, "20260301T010000Z.json.gz"),
        {"providers": [mk_provider("new%d" % i) for i in range(20)]},
    )
    write_json_gz(
        os.path.join(stats_dir, "20260301T020000Z.json.gz"),
        {"providers": [mk_provider("new%d" % i) for i in range(22)]},
    )

    releases_path = os.path.join(root, "releases.json")
    with open(releases_path, "w") as f:
        json.dump(
            [{"tag": "v2.0.0", "published_at": "2026-03-01T01:30:00Z"}], f,
        )

    return raw_dir, releases_path


def _build_zero_event_raw_dir(root):
    """A raw dir with gradual 5%-per-snapshot churn (below the 50% restart
    threshold) and no releases inside the span, for U5."""
    raw_dir = os.path.join(root, "raw")
    stats_dir = os.path.join(raw_dir, "stats")
    os.makedirs(stats_dir)

    base = datetime(2026, 4, 1, 0, 0, 0, tzinfo=timezone.utc)
    ids = list(range(100))
    next_id = 100
    for i in range(6):
        t = base + timedelta(minutes=5 * i)
        providers = [mk_provider("p%d" % j) for j in ids]
        name = t.strftime("%Y%m%dT%H%M%S") + "Z.json.gz"
        write_json_gz(os.path.join(stats_dir, name), {"providers": providers})
        ids = ids[5:] + list(range(next_id, next_id + 5))
        next_id += 5

    releases_path = os.path.join(root, "releases.json")
    _write_empty_releases(releases_path)

    return raw_dir, releases_path


class BuildReportIndexHtmlTests(unittest.TestCase):
    def test_U3_embedded_json_equals_computed_timeline_events_stuck_now_span(self):
        with tempfile.TemporaryDirectory() as root:
            raw_dir, releases_path = _build_event_bearing_raw_dir(root)
            out_dir = os.path.join(root, "out")

            result = build_report(raw_dir, releases_path, out_dir)

            index_path = os.path.join(out_dir, "index.html")
            self.assertTrue(
                os.path.isfile(index_path),
                "build_report must write out_dir/index.html",
            )
            with open(index_path, encoding="utf-8") as f:
                html = f.read()

            # Everything below re-derives the expected values from raw_dir
            # and out_dir, so it must stay inside the TemporaryDirectory
            # block while those paths still exist.
            embedded = extract_embedded_json(html)
            for key in ("timeline", "events", "stuck_now", "span"):
                self.assertIn(
                    key, embedded, "embedded data missing key %r" % (key,)
                )

            snapshots, _skipped = load_stats(raw_dir)

            expected_timeline = build_timeline(snapshots)
            self.assertEqual(
                embedded["timeline"], expected_timeline,
                "embedded timeline must equal report.timeline.build_timeline "
                "over the same snapshots",
            )

            self.assertEqual(
                embedded["stuck_now"], result["stuck_now"],
                "embedded stuck_now must equal build_report's returned "
                "stuck_now",
            )

            self.assertEqual(len(result["events"]), 2, "test fixture expects "
                              "a restart and a release event")
            expected_events = []
            for e in result["events"]:
                at_dt = parse_iso_utc(e["at"])
                w = event_window(snapshots, at_dt)
                expected_event = dict(e)
                expected_event["window"] = w["window"]
                expected_event["chips_before"] = w["chips_before"]
                expected_events.append(expected_event)

            self.assertEqual(
                embedded["events"], expected_events,
                "each embedded event must equal the corresponding "
                "events.json entry plus 'window' and 'chips_before' merged "
                "in, computed by report.timeline.event_window over the "
                "same snapshots",
            )

            # events.json itself must stay unchanged -- no window/chips_before.
            events_json_path = os.path.join(out_dir, "events.json")
            with open(events_json_path) as f:
                written_events = json.load(f)
            for ev in written_events:
                self.assertNotIn(
                    "window", ev,
                    "events.json must not change shape: no 'window' key",
                )
                self.assertNotIn(
                    "chips_before", ev,
                    "events.json must not change shape: no 'chips_before' "
                    "key",
                )

            expected_span = {
                "start": iso_utc(snapshots[0][0]),
                "end": iso_utc(snapshots[-1][0]),
                "snapshots": len(snapshots),
            }
            self.assertEqual(embedded["span"], expected_span)

    def test_U4_index_html_has_no_urls_or_external_script_or_link_tags(self):
        with tempfile.TemporaryDirectory() as root:
            raw_dir, releases_path = _build_event_bearing_raw_dir(root)
            out_dir = os.path.join(root, "out")
            build_report(raw_dir, releases_path, out_dir)

            with open(os.path.join(out_dir, "index.html"), encoding="utf-8") as f:
                html = f.read()

        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)
        self.assertNotIn("<script src", html)
        self.assertNotIn("<link", html)

    def test_U5_zero_events_page_written_with_no_events_line(self):
        with tempfile.TemporaryDirectory() as root:
            raw_dir, releases_path = _build_zero_event_raw_dir(root)
            out_dir = os.path.join(root, "out")

            result = build_report(raw_dir, releases_path, out_dir)
            self.assertEqual(
                result["events"], [],
                "test fixture is designed to produce zero events",
            )

            index_path = os.path.join(out_dir, "index.html")
            self.assertTrue(os.path.isfile(index_path))
            with open(index_path, encoding="utf-8") as f:
                html = f.read()

        self.assertIn(
            "No restart or release was seen in the recorded span.", html,
        )

    def test_U6_real_data_fixture_under_500kb_with_expected_restart_event(self):
        if not os.path.isdir(FIXTURE_RAW_DIR):
            self.fail(
                "committed fixture not found at %s" % (FIXTURE_RAW_DIR,)
            )

        with tempfile.TemporaryDirectory() as out_dir:
            build_report(FIXTURE_RAW_DIR, FIXTURE_RELEASES_PATH, out_dir)

            index_path = os.path.join(out_dir, "index.html")
            self.assertTrue(os.path.isfile(index_path))

            size = os.path.getsize(index_path)
            self.assertLess(
                size, 500 * 1024,
                "index.html for the recorded restart fixture must be "
                "under 500 KB, got %d bytes" % (size,),
            )

            with open(index_path, encoding="utf-8") as f:
                html = f.read()

        embedded = extract_embedded_json(html)
        event_times = [e["at"] for e in embedded.get("events", [])]
        self.assertIn(
            "2026-09-28T20:42:37Z", event_times,
            "expected the coordinator restart event at 2026-09-28T20:42:37Z "
            "in the embedded events, got: %r" % (event_times,),
        )


if __name__ == "__main__":
    unittest.main()
