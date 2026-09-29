"""Failing-first tests for the permanent event log (report/history.py,
wilt.py --history, build_report(history_path=...), publish workflow).
"""
import copy
import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from report.write import build_report
import wilt

HERE = os.path.dirname(__file__)
ROOT = os.path.dirname(HERE)
RAW_DIR = os.path.join(HERE, "fixtures", "restart_20260928")
RELEASES_PATH = os.path.join(HERE, "fixtures", "releases.json")
PUBLISH_YML = os.path.join(ROOT, ".github", "workflows", "publish.yml")

RESTART_AT = "2026-09-28T20:42:37Z"


def _dt(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def mk_event(at="2026-09-28T20:42:37Z", kind="restart",
             label="coordinator restart", baseline=1000.0, **over):
    e = {
        "kind": kind,
        "at": at,
        "label": label,
        "baseline_macs": baseline,
        "min_macs_after": 0,
        "drop": baseline,
        "recovery_minutes": 1.5,
        "requests_per_min_before": 100.0,
        "requests_per_min_after": 110.0,
        "stuck_before": 3,
        "stuck_after": 3,
        "stuck_carried": 2,
        "stuck_by_chip": {"M4": 3},
    }
    e.update(over)
    return e


def mk_stored(at="2026-09-28T20:42:37Z", final=False,
              recorded_at="2026-09-28T21:00:00Z", **kw):
    e = mk_event(at=at, **kw)
    e["final"] = final
    e["recorded_at"] = recorded_at
    return e


def _key(e):
    return (e["kind"], e["at"], e["label"])


def _import_history():
    from report import history  # raises ImportError until implemented
    return history


class MergeHistoryTests(unittest.TestCase):
    def test_H1_new_event_added_not_final_before_window_closes(self):
        h = _import_history()
        at = _dt(RESTART_AT)
        computed = [mk_event()]
        out = h.merge_history([], computed, at + timedelta(hours=1))
        self.assertEqual(len(out), 1)
        self.assertEqual(_key(out[0]), ("restart", RESTART_AT, "coordinator restart"))
        self.assertIs(out[0]["final"], False)
        self.assertEqual(out[0]["baseline_macs"], 1000.0)
        self.assertIn("recorded_at", out[0])

    def test_H1_new_event_added_final_when_window_already_closed(self):
        h = _import_history()
        at = _dt(RESTART_AT)
        out = h.merge_history([], [mk_event()], at + timedelta(hours=3, minutes=30))
        self.assertEqual(len(out), 1)
        self.assertIs(out[0]["final"], True)

    def test_H1_just_before_threshold_is_not_final(self):
        h = _import_history()
        at = _dt(RESTART_AT)
        out = h.merge_history(
            [], [mk_event()], at + timedelta(hours=3, minutes=29, seconds=59))
        self.assertIs(out[0]["final"], False)

    def test_H2_non_final_event_replaced_by_recomputed_values(self):
        h = _import_history()
        at = _dt(RESTART_AT)
        existing = [mk_stored(final=False, baseline=1000.0)]
        computed = [mk_event(baseline=1234.5, recovery_minutes=9.0)]
        out = h.merge_history(existing, computed, at + timedelta(hours=2))
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["baseline_macs"], 1234.5)
        self.assertEqual(out[0]["recovery_minutes"], 9.0)
        self.assertIs(out[0]["final"], False)

    def test_H3_becomes_final_then_frozen(self):
        h = _import_history()
        at = _dt(RESTART_AT)
        existing = [mk_stored(final=False, baseline=1000.0)]
        computed = [mk_event(baseline=1111.0)]
        out = h.merge_history(existing, computed, at + timedelta(hours=3, minutes=30))
        self.assertEqual(len(out), 1)
        self.assertIs(out[0]["final"], True)
        self.assertEqual(out[0]["baseline_macs"], 1111.0)

        later = h.merge_history(
            out, [mk_event(baseline=9999.0, drop=9999.0)], at + timedelta(hours=8))
        self.assertEqual(len(later), 1)
        self.assertIs(later[0]["final"], True)
        self.assertEqual(later[0]["baseline_macs"], 1111.0)
        self.assertEqual(later[0]["drop"], 1111.0)
        self.assertEqual(later[0], out[0])

    def test_H3_stored_final_event_never_changed_even_if_window_check_would_differ(self):
        h = _import_history()
        existing = [mk_stored(final=True, baseline=500.0)]
        out = h.merge_history(
            existing, [mk_event(baseline=600.0)], _dt(RESTART_AT) + timedelta(minutes=10))
        self.assertEqual(out, existing)

    def test_H4_absent_from_computed_kept_and_marked_final(self):
        h = _import_history()
        existing = [mk_stored(final=False, baseline=321.0)]
        out = h.merge_history(existing, [], _dt("2026-10-20T00:00:00Z"))
        self.assertEqual(len(out), 1)
        self.assertIs(out[0]["final"], True)
        for k, v in existing[0].items():
            if k == "final":
                continue
            self.assertEqual(out[0][k], v, k)

    def test_merge_sorted_ascending_and_keyed_by_kind_at_label(self):
        h = _import_history()
        a = mk_event(at="2026-09-28T20:42:37Z")
        b = mk_event(at="2026-09-20T10:00:00Z", kind="release", label="v1.0.0")
        c = mk_event(at="2026-09-28T20:42:37Z", kind="release", label="v2.0.0")
        out = h.merge_history([], [a, b, c], _dt("2026-09-30T00:00:00Z"))
        self.assertEqual(len(out), 3)
        ats = [e["at"] for e in out]
        self.assertEqual(ats, sorted(ats))
        self.assertEqual(len(set(_key(e) for e in out)), 3)

    def test_merge_does_not_mutate_inputs(self):
        h = _import_history()
        existing = [mk_stored(final=False)]
        computed = [mk_event(baseline=5.0)]
        e0, c0 = copy.deepcopy(existing), copy.deepcopy(computed)
        h.merge_history(existing, computed, _dt("2026-09-29T00:00:00Z"))
        self.assertEqual(existing, e0)
        self.assertEqual(computed, c0)


class DeterminismAndIoTests(unittest.TestCase):
    def test_H5_same_inputs_give_byte_identical_file(self):
        h = _import_history()
        existing = [mk_stored(at="2026-09-20T10:00:00Z", final=True, kind="release",
                              label="v1.0.0"),
                    mk_stored(final=False)]
        computed = [mk_event(baseline=1500.0),
                    mk_event(at="2026-09-29T01:00:00Z", kind="release", label="v3")]
        data_end = _dt("2026-09-29T02:00:00Z")
        with tempfile.TemporaryDirectory() as d:
            p1, p2 = os.path.join(d, "a.jsonl"), os.path.join(d, "b.jsonl")
            h.write_history(p1, h.merge_history(copy.deepcopy(existing),
                                                copy.deepcopy(computed), data_end))
            h.write_history(p2, h.merge_history(copy.deepcopy(existing),
                                                copy.deepcopy(computed), data_end))
            with open(p1, "rb") as f1, open(p2, "rb") as f2:
                b1, b2 = f1.read(), f2.read()
        self.assertEqual(b1, b2)
        self.assertGreater(len(b1), 0)

    def test_write_history_one_json_object_per_line_and_roundtrips(self):
        h = _import_history()
        events = [mk_stored(at="2026-09-20T10:00:00Z", final=True),
                  mk_stored(final=False)]
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "sub_events.jsonl")
            h.write_history(p, events)
            with open(p, encoding="utf-8") as f:
                text = f.read()
            self.assertTrue(text.endswith("\n"))
            lines = text.splitlines()
            self.assertEqual(len(lines), 2)
            self.assertEqual([json.loads(x) for x in lines], events)
            self.assertEqual(h.load_history(p), events)
            self.assertEqual(sorted(os.listdir(d)), ["sub_events.jsonl"],
                             "atomic write must leave no temp file behind")

    def test_load_history_missing_file_returns_empty_list(self):
        h = _import_history()
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(h.load_history(os.path.join(d, "nope.jsonl")), [])

    def test_H6_malformed_line_raises_naming_line_number(self):
        h = _import_history()
        good = json.dumps(mk_stored())
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "events.jsonl")
            with open(p, "w", encoding="utf-8") as f:
                f.write(good + "\n" + good + "\n" + "{not json\n" + good + "\n")
            with self.assertRaises(Exception) as cm:
                h.load_history(p)
        self.assertIn("3", str(cm.exception))
        self.assertIn("line", str(cm.exception).lower())


class WiltCliHistoryTests(unittest.TestCase):
    def _run(self, hist, out):
        return wilt.main([
            "--raw", RAW_DIR, "--releases", RELEASES_PATH,
            "--out", out, "--history", hist,
        ])

    def test_H7_end_to_end_one_line_and_second_run_byte_identical(self):
        with tempfile.TemporaryDirectory() as d:
            hist = os.path.join(d, "history", "events.jsonl")
            os.makedirs(os.path.dirname(hist))
            out1, out2 = os.path.join(d, "o1"), os.path.join(d, "o2")

            self.assertEqual(self._run(hist, out1), 0)
            with open(hist, "rb") as f:
                first = f.read()
            lines = [ln for ln in first.decode("utf-8").splitlines() if ln.strip()]
            self.assertEqual(len(lines), 1)
            rec = json.loads(lines[0])
            self.assertEqual(rec["kind"], "restart")
            self.assertEqual(rec["at"], RESTART_AT)
            self.assertEqual(rec["label"], "coordinator restart")
            self.assertIn("final", rec)
            self.assertIn("recorded_at", rec)
            self.assertEqual(rec["stuck_carried"], 6)

            self.assertEqual(self._run(hist, out2), 0)
            with open(hist, "rb") as f:
                second = f.read()
            self.assertEqual(first, second)

            with open(os.path.join(out2, "events.json")) as f:
                events = json.load(f)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["at"], RESTART_AT)

    def test_H7_history_file_merges_into_events_json_and_markdown(self):
        with tempfile.TemporaryDirectory() as d:
            hist = os.path.join(d, "events.jsonl")
            old = mk_stored(at="2026-09-10T08:00:00Z", final=True,
                            kind="release", label="v0.0.1", baseline=42.0)
            with open(hist, "w", encoding="utf-8") as f:
                f.write(json.dumps(old, sort_keys=True) + "\n")
            out = os.path.join(d, "o")
            self.assertEqual(self._run(hist, out), 0)
            with open(os.path.join(out, "events.json")) as f:
                events = json.load(f)
            self.assertEqual(sorted(e["at"] for e in events),
                             ["2026-09-10T08:00:00Z", RESTART_AT])
            with open(os.path.join(out, "EVENTS.md")) as f:
                md = f.read()
            self.assertIn("v0.0.1", md)
            with open(hist, encoding="utf-8") as f:
                self.assertEqual(len([x for x in f.read().splitlines() if x]), 2)

    def test_build_report_history_path_keyword(self):
        with tempfile.TemporaryDirectory() as d:
            hist = os.path.join(d, "events.jsonl")
            res = build_report(RAW_DIR, RELEASES_PATH, os.path.join(d, "o"),
                               history_path=hist)
            self.assertTrue(os.path.isfile(hist))
            self.assertEqual(len(res["events"]), 1)

    def test_without_history_behaviour_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            res = build_report(RAW_DIR, RELEASES_PATH, d)
            self.assertEqual(len(res["events"]), 1)
            self.assertNotIn("final", res["events"][0])
            self.assertEqual(os.listdir(d).count("events.jsonl"), 0)


class PageHistoryTests(unittest.TestCase):
    def _page(self, stored_events):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        hist = os.path.join(d, "events.jsonl")
        with open(hist, "w", encoding="utf-8") as f:
            for e in stored_events:
                f.write(json.dumps(e, sort_keys=True) + "\n")
        out = os.path.join(d, "o")
        build_report(RAW_DIR, RELEASES_PATH, out, history_path=hist)
        with open(os.path.join(out, "index.html"), encoding="utf-8") as f:
            return f.read()

    def test_H8_newest_event_without_window_shows_aged_out_and_table_row(self):
        # Newer than every snapshot in the fixture, so it is the newest
        # event in history and has no window in the current data.
        gone = mk_stored(at="2026-09-29T10:00:00Z", final=True, kind="release",
                         label="v9.9.9-agedout", baseline=777.7, drop=333.3)
        html = self._page([gone])
        self.assertIn("snapshot detail has aged out", html)
        self.assertIn("v9.9.9-agedout", html)
        self.assertIn("2026-09-29 10:00:00", html)
        self.assertIn("777.7", html)
        self.assertIn("2026-09-28 20:42:37", html)  # fixture restart still listed
        self.assertIn("events scored since", html)

    def test_H8_older_event_listed_in_table_without_aged_out_statement(self):
        # An older event outside the data: sections 3 to 5 keep using the
        # newest event that has a window, so no aged-out statement.
        gone = mk_stored(at="2026-09-20T10:00:00Z", final=True, kind="release",
                         label="v0.0.9-old", baseline=777.7)
        html = self._page([gone])
        self.assertIn("v0.0.9-old", html)
        self.assertIn("2026-09-20 10:00:00", html)
        self.assertIn("777.7", html)
        self.assertNotIn("snapshot detail has aged out", html)
        self.assertIn("2 events scored since 2026-09-20", html)


class PublishWorkflowTests(unittest.TestCase):
    def test_H9_publish_runs_with_history_and_stages_it(self):
        with open(PUBLISH_YML, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("wilt.py", text)
        self.assertIn("--history history/events.jsonl", text)
        self.assertIn("git add", text)
        add_lines = [ln for ln in text.splitlines() if "git add" in ln]
        self.assertTrue(
            any("history/events.jsonl" in ln for ln in add_lines),
            "history/events.jsonl must be staged by a git add line: %r" % add_lines,
        )
        self.assertTrue(
            any("site/index.html" in ln for ln in add_lines),
            "site/index.html must still be staged",
        )


if __name__ == "__main__":
    unittest.main()
