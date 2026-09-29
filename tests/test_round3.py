"""Regression tests for the round 3 review findings and the wilt rename.

Principle: a gap or a missing observation is never shown or computed as zero.
"""
import gzip
import json
import os
import random
import re
import tempfile
import unittest
import zlib
from datetime import datetime, timedelta, timezone

from detect.snapshots import load_stats
from measure.metrics import _rate, measure_event
from report.page import render_page
from report.timeline import event_window
from report.write import build_report
from tests._helpers import (extract_embedded_json, iso_utc, mk_provider,
                            write_json_gz)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = datetime(2026, 4, 1, 0, 0, 0, tzinfo=timezone.utc)


def _read(path, mode="r"):
    with open(path, mode) as f:
        return f.read()


def _stamp(dt):
    return dt.strftime("%Y%m%dT%H%M%SZ")


def _write_run(raw, snaps):
    """snaps: list of (datetime, providers). Writes raw/stats/*.json.gz and a
    releases file; returns the releases path."""
    stats = os.path.join(raw, "stats")
    os.makedirs(stats, exist_ok=True)
    for t, providers in snaps:
        write_json_gz(os.path.join(stats, _stamp(t) + ".json.gz"),
                      {"providers": providers})
    rel = os.path.join(raw, "releases.json")
    with open(rel, "w") as f:
        json.dump([], f)
    return rel


def _fleet(prefix, n, rs=1000, **kw):
    return [mk_provider("%s%d" % (prefix, i), requests_served=rs, **kw)
            for i in range(n)]


class CorruptedZlibTests(unittest.TestCase):
    def test_flipped_compressed_bytes_are_skipped_and_counted(self):
        rnd = random.Random(7)
        providers = [
            mk_provider("id-%06d" % rnd.randrange(10 ** 6),
                        requests_served=rnd.randrange(10 ** 7),
                        tokens_generated=rnd.randrange(10 ** 9))
            for _ in range(400)
        ]
        with tempfile.TemporaryDirectory() as d:
            stats = os.path.join(d, "stats")
            os.makedirs(stats)
            good = os.path.join(stats, "20260401T000000Z.json.gz")
            bad = os.path.join(stats, "20260401T000500Z.json.gz")
            write_json_gz(good, {"providers": providers})
            write_json_gz(bad, {"providers": providers})
            raw = bytearray(_read(bad, "rb"))
            for i in range(20, 61):
                raw[i] ^= 0xFF
            with open(bad, "wb") as f:
                f.write(bytes(raw))
            # the corruption must surface as zlib.error, the case that
            # escaped the old (OSError, ValueError, EOFError) handler
            with self.assertRaises(zlib.error):
                with gzip.open(bad, "rb") as f:
                    f.read()
            snapshots, skipped = load_stats(d)
        self.assertEqual(skipped, 1)
        self.assertEqual(len(snapshots), 1)


class RateNoSharedIdsTests(unittest.TestCase):
    def test_rate_is_none_when_no_pair_shares_an_id(self):
        empty = []
        self.assertIsNone(_rate([(empty, _fleet("a", 3), 5.0)]))
        self.assertIsNone(_rate([(_fleet("a", 3), empty, 5.0)]))
        self.assertIsNone(_rate([(_fleet("a", 3), _fleet("b", 3), 5.0)]))
        self.assertIsNone(_rate([]))

    def test_empty_snapshot_in_after_window_adds_neither_work_nor_minutes(self):
        at = BASE + timedelta(minutes=60)
        snaps = [
            (BASE + timedelta(minutes=50), _fleet("a", 10, rs=1000)),
            (at, _fleet("a", 10, rs=1000)),
            # +10 min: 10 ids, +100 requests each
            (at + timedelta(minutes=10), _fleet("a", 10, rs=1100)),
            # empty snapshot: pairs on both sides share no ids
            (at + timedelta(minutes=15), []),
            # after the restart: new ids, so the empty->new pair shares none
            (at + timedelta(minutes=20), _fleet("n", 10, rs=5000)),
            (at + timedelta(minutes=30), _fleet("n", 10, rs=5100)),
        ]
        m = measure_event(snaps, at)
        # counted pairs: at->+10 (1000 req, 10 min) and +20->+30 (1000, 10 min)
        self.assertAlmostEqual(m["requests_per_min_after"], 2000 / 20.0, places=6)

    def test_no_contributing_pair_is_null_in_metrics_and_outputs(self):
        with tempfile.TemporaryDirectory() as d:
            at = BASE + timedelta(minutes=10)
            rel = _write_run(d, [
                (BASE, _fleet("a", 5)),
                (at, []),
                (at + timedelta(minutes=5), _fleet("b", 5)),
            ])
            out = os.path.join(d, "out")
            build_report(d, rel, out)
            events = json.loads(_read(os.path.join(out, "events.json")))
            md = _read(os.path.join(out, "EVENTS.md"))
            html = _read(os.path.join(out, "index.html"))
        self.assertEqual(len(events), 1)
        self.assertIsNone(events[0]["requests_per_min_after"])
        self.assertIsNone(events[0]["requests_per_min_before"])
        row = [l for l in md.splitlines() if l.startswith("| restart")][0]
        cells = [c.strip() for c in row.strip("|").split("|")]
        self.assertEqual(cells[7], "-")
        self.assertEqual(cells[8], "-")
        self.assertIn("no measurement", html)


class EmptyWindowTests(unittest.TestCase):
    def _data(self, event_extra, timeline=None, stuck_now=None):
        ev = {
            "kind": "restart", "at": "2026-04-01T00:10:00Z",
            "label": "coordinator restart", "baseline_macs": None,
            "min_macs_after": None, "drop": None, "recovery_minutes": None,
            "requests_per_min_before": None, "requests_per_min_after": None,
            "stuck_before": None, "stuck_after": None, "stuck_carried": None,
            "stuck_by_chip": {},
        }
        ev.update(event_extra)
        tl = timeline if timeline is not None else [
            {"t": "2026-04-01T00:00:00Z", "macs": 3, "stuck": 0, "rpm": None}]
        return {
            "timeline": tl, "events": [ev],
            "stuck_now": stuck_now or {"at": "2026-04-01T00:00:00Z", "count": 0, "by_chip": {}},
            "span": {"start": "2026-04-01T00:00:00Z", "end": "2026-04-01T00:00:00Z", "snapshots": 1},
        }

    def test_empty_window_says_no_snapshots_and_shows_no_clock_or_zero_macs(self):
        html = render_page(self._data({"window": [], "chips_before": {"M3": 3}}))
        self.assertIn("no snapshots in this window", html)
        self.assertNotIn('id="ev-clock"', html)
        self.assertNotIn('id="ev-macs"', html)
        sec = re.search(r'<section class="tall" id="s-event".*?</section>', html, re.S).group(0)
        self.assertNotIn("00:00:00", sec)
        self.assertNotIn("Macs online", sec)

    def test_window_with_data_still_has_clock_and_counter(self):
        w = [{"t": "2026-04-01T00:00:00Z", "macs": 3, "stuck": 0, "rpm": None}]
        html = render_page(self._data({"window": w, "chips_before": {"M3": 3}}))
        self.assertIn('id="ev-clock"', html)
        self.assertIn('id="ev-macs"', html)
        sec = re.search(r'<section class="tall" id="s-event".*?</section>', html, re.S).group(0)
        self.assertNotIn("no snapshots in this window", sec)


class NoSnapshotsTests(unittest.TestCase):
    def test_zero_readable_snapshots_no_1970_and_says_so(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "stats"))
            rel = os.path.join(d, "r.json")
            with open(rel, "w") as f:
                f.write("[]")
            out = os.path.join(d, "out")
            res = build_report(d, rel, out)
            html = _read(os.path.join(out, "index.html"))
            md = _read(os.path.join(out, "EVENTS.md"))
        self.assertIsNone(res["stuck_now"]["count"])
        body = html.split("</main>")[0]
        self.assertGreaterEqual(body.count("No readable snapshots."), 2)
        self.assertNotIn("1970", html)
        self.assertIn("no measurement", md)
        # the script must not build a date from a 0 timestamp
        self.assertNotIn(": 0);", html.split('id="wilt-data"')[1].split("</script>", 1)[1])


class ChipsBeforeTests(unittest.TestCase):
    def test_no_snapshot_before_event_gives_null_chips_before(self):
        snaps = [(BASE, _fleet("a", 3)), (BASE + timedelta(minutes=5), _fleet("a", 3))]
        self.assertIsNone(event_window(snaps, BASE)["chips_before"])
        self.assertEqual(event_window(snaps, BASE + timedelta(minutes=1))["chips_before"],
                         {"M3": 3})

    def test_fleet_section_says_no_snapshot_before_not_zero_macs(self):
        data = EmptyWindowTests()._data({
            "window": [{"t": "2026-04-01T00:10:00Z", "macs": 3, "stuck": 0, "rpm": None}],
            "chips_before": None,
        })
        html = render_page(data)
        m = re.search(r'<h2 id="fleet-title"[^>]*>(.*?)</h2>', html)
        self.assertEqual(m.group(1), "No snapshot before this event was recorded.")

    def test_fleet_section_with_chips_has_no_static_message(self):
        data = EmptyWindowTests()._data({"window": [], "chips_before": {"M3": 3}})
        html = render_page(data)
        m = re.search(r'<h2 id="fleet-title"[^>]*>(.*?)</h2>', html)
        self.assertEqual(m.group(1), "")


class StuckNowNullTests(unittest.TestCase):
    def _run(self, snaps):
        d = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(d, ignore_errors=True))
        rel = _write_run(d, snaps)
        out = os.path.join(d, "out")
        res = build_report(d, rel, out)
        return (res, _read(os.path.join(out, "index.html")),
                _read(os.path.join(out, "EVENTS.md")))

    def test_last_snapshot_empty_stuck_now_is_null(self):
        res, html, md = self._run([
            (BASE, _fleet("a", 5, runtime_verified=False)),
            (BASE + timedelta(minutes=5), []),
        ])
        self.assertIsNone(res["stuck_now"]["count"])
        self.assertEqual(res["stuck_now"]["by_chip"], {})
        self.assertEqual(extract_embedded_json(html)["stuck_now"]["count"], None)
        hero = re.search(r'<p class="hero" id="hero">(.*?)</p>', html).group(1)
        self.assertEqual(hero, "-")
        self.assertIn("The last snapshot has no providers, so there is no stuck count.", html)
        self.assertIn("Stuck now (as of 2026-04-01T00:05:00Z): no measurement", md)

    def test_stuck_now_with_providers_is_still_a_count(self):
        res, html, md = self._run([
            (BASE, _fleet("a", 5, runtime_verified=False)),
            (BASE + timedelta(minutes=5), _fleet("a", 5, runtime_verified=False)),
        ])
        self.assertEqual(res["stuck_now"]["count"], 5)
        self.assertEqual(re.search(r'<p class="hero" id="hero">(.*?)</p>', html).group(1), "5")

    def test_genuine_zero_stuck_is_zero(self):
        res, html, _ = self._run([(BASE, _fleet("a", 5)), (BASE + timedelta(minutes=5), _fleet("a", 5))])
        self.assertEqual(res["stuck_now"]["count"], 0)
        self.assertEqual(re.search(r'<p class="hero" id="hero">(.*?)</p>', html).group(1), "0")


class HeroTests(unittest.TestCase):
    def test_no_count_up_animation(self):
        html = render_page(EmptyWindowTests()._data({"window": [], "chips_before": {"M3": 3}},
                           stuck_now={"at": "2026-04-01T00:00:00Z", "count": 7, "by_chip": {"M3": 7}}))
        self.assertNotIn("count-up", html)
        self.assertNotIn("getElementById('hero')", html)
        self.assertNotIn("$('hero')", html)
        self.assertRegex(html, r'<p class="hero" id="hero">7</p>')


class RenameTests(unittest.TestCase):
    OLD = "deploy" + "watch"

    def test_no_old_name_anywhere(self):
        hits = []
        for dp, dns, fns in os.walk(ROOT):
            dns[:] = [x for x in dns if x != ".git" and x != "__pycache__"
                      and not (dp == ROOT and x.startswith("out"))]
            for fn in fns:
                if self.OLD in fn.lower():
                    hits.append(os.path.join(dp, fn))
                if fn.endswith(".pyc"):
                    continue
                p = os.path.join(dp, fn)
                try:
                    txt = _read(p)
                except (UnicodeDecodeError, OSError):
                    continue
                if self.OLD in txt.lower():
                    hits.append(p)
        self.assertEqual(hits, [])

    def test_cli_file_and_page_identity(self):
        self.assertTrue(os.path.isfile(os.path.join(ROOT, "wilt.py")))
        self.assertFalse(os.path.exists(os.path.join(ROOT, self.OLD + ".py")))
        html = render_page(EmptyWindowTests()._data({"window": [], "chips_before": {"M3": 3}}))
        self.assertIn("<title>wilt</title>", html)
        self.assertIn('id="name">wilt</h1>', html)
        self.assertIn('id="wilt-data"', html)
        self.assertIn("Macs it leaves wilted.", html)


class M6Tests(unittest.TestCase):
    def test_m6_is_in_the_fixed_order_with_its_own_colour(self):
        html = render_page(EmptyWindowTests()._data({"window": [], "chips_before": {"M6": 2}}))
        self.assertIn("var CHIPS = ['M1', 'M2', 'M3', 'M4', 'M5', 'M6', 'other'];", html)
        self.assertRegex(html, r"--m6:#[0-9a-f]{6};")
        self.assertIn("M6: cv('--m6')", html)
        cols = re.findall(r"--(m[1-6]|other):(#[0-9a-f]{6})", html)
        self.assertEqual(len(set(c for _, c in cols)), 7)


if __name__ == "__main__":
    unittest.main()
