"""Regression tests for edge cases in loading and event detection.

Each test class below is one numbered finding from the review:
  A1 - a .json.gz truncated at the byte level (the gzip container itself is
       cut short, e.g. by `head -c N`) must be skipped and counted, not
       raise EOFError out of load_stats.
  A2 - find_restarts must flag an empty FIRST snapshot at its own time; the
       loop must not start at index 1 and fire one snapshot late.
  A3 - find_releases must accept raw `gh api repos/OWNER/REPO/releases`
       objects (which key the tag as "tag_name", not "tag") as well as the
       "tag" shape already used by tests/fixtures/releases.json, and must
       skip -- not crash on -- entries whose "published_at" is null
       (unpublished drafts).
  A4 - restart events built by report/write.py must carry the label
       "coordinator restart", not "restart"; release events keep their tag
       as the label, unchanged.
"""
import gzip
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from detect.events import find_releases, find_restarts
from detect.snapshots import load_stats
from report.write import build_report

from tests._helpers import mk_provider, write_json_gz


def write_byte_truncated_json_gz(path, obj, keep_fraction=0.5):
    """Write a complete, valid .json.gz, then cut the file's own bytes
    short -- this is what `head -c N realfile.json.gz` produces: a gzip
    container whose compressed stream itself ends early (raises EOFError
    from the gzip module), which is a different failure mode from a valid
    gzip container wrapping truncated JSON text (raises json.JSONDecodeError,
    already handled -- see tests/test_detect.py T7)."""
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(obj, f)
    with open(path, "rb") as f:
        full = f.read()
    cut = int(len(full) * keep_fraction)
    with open(path, "wb") as f:
        f.write(full[:cut])


class A1ByteTruncatedGzipTests(unittest.TestCase):
    def test_A1_byte_truncated_gzip_is_skipped_not_eoferror(self):
        with tempfile.TemporaryDirectory() as d:
            stats_dir = os.path.join(d, "stats")
            os.makedirs(stats_dir)

            write_json_gz(
                os.path.join(stats_dir, "20260928T060000Z.json.gz"),
                {"providers": [mk_provider("a")]},
            )
            write_json_gz(
                os.path.join(stats_dir, "20260928T060200Z.json.gz"),
                {"providers": [mk_provider("b"), mk_provider("c")]},
            )
            write_byte_truncated_json_gz(
                os.path.join(stats_dir, "20260928T060400Z.json.gz"),
                {"providers": [mk_provider("d%d" % i) for i in range(200)]},
                keep_fraction=0.5,
            )

            try:
                snapshots, skipped = load_stats(d)
            except EOFError as e:
                self.fail(
                    "load_stats must catch a byte-level-truncated gzip "
                    "container and count it as skipped, not let EOFError "
                    "propagate: %r" % (e,)
                )

        self.assertEqual(
            skipped, 1,
            "the byte-truncated file must be counted as skipped",
        )
        self.assertEqual(
            len(snapshots), 2,
            "the two valid snapshots must still load despite the "
            "byte-truncated one",
        )


class A2FindRestartsFirstSnapshotTests(unittest.TestCase):
    def test_A2_empty_first_snapshot_alone_flags_at_its_own_time(self):
        t0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        snapshots = [(t0, [])]

        restarts = find_restarts(snapshots)

        self.assertEqual(
            restarts, [t0],
            "an empty snapshot that is the very first snapshot in the "
            "recording must still be flagged as a restart at its own "
            "time; today's loop starts at index 1 so a lone empty first "
            "snapshot is never even examined",
        )

    def test_A2_empty_first_snapshot_followed_by_new_ids_fires_at_first_not_second(self):
        t0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        t1 = t0 + timedelta(minutes=5)  # within the 10-minute merge window
        new_ids = [mk_provider("new%d" % i) for i in range(20)]

        snapshots = [(t0, []), (t1, new_ids)]

        restarts = find_restarts(snapshots)

        self.assertEqual(
            restarts, [t0],
            "the restart must be timestamped at the empty snapshot (t0), "
            "not one snapshot late at t1; today's implementation only "
            "compares snapshots[1] against snapshots[0] and reports the "
            "event at snapshots[1]'s time instead",
        )


class A3FindReleasesRawGhApiShapeTests(unittest.TestCase):
    def test_A3_accepts_tag_name_key_from_raw_gh_api_releases(self):
        start = datetime(2026, 9, 1, 0, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 9, 30, 0, 0, 0, tzinfo=timezone.utc)
        # Shape of a raw `gh api repos/OWNER/REPO/releases` object: no
        # "tag" key at all, only "tag_name".
        releases = [
            {"tag_name": "v1.0.0", "published_at": "2026-09-15T12:00:00Z"},
        ]

        try:
            result = find_releases(releases, start, end)
        except Exception as e:
            self.fail(
                "find_releases must accept the raw gh api shape keyed "
                "\"tag_name\" (no \"tag\"), not raise: %r" % (e,)
            )

        self.assertEqual(
            len(result), 1,
            "a raw gh api release object (tag_name, no tag) must still "
            "produce one release event, got: %r" % (result,),
        )
        at, tag = result[0]
        self.assertEqual(tag, "v1.0.0")
        self.assertEqual(at, datetime(2026, 9, 15, 12, 0, 0, tzinfo=timezone.utc))

    def test_A3_still_accepts_tag_key_shape(self):
        start = datetime(2026, 9, 1, 0, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 9, 30, 0, 0, 0, tzinfo=timezone.utc)
        releases = [
            {"tag": "v1.0.0", "published_at": "2026-09-15T12:00:00Z"},
        ]

        result = find_releases(releases, start, end)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][1], "v1.0.0")

    def test_A3_skips_draft_with_null_published_at_instead_of_crashing(self):
        start = datetime(2026, 9, 1, 0, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 9, 30, 0, 0, 0, tzinfo=timezone.utc)
        releases = [
            {"tag_name": "v1.1.0-draft", "published_at": None},
            {"tag_name": "v1.0.0", "published_at": "2026-09-15T12:00:00Z"},
        ]

        try:
            result = find_releases(releases, start, end)
        except Exception as e:
            self.fail(
                "a draft release with published_at=null must be skipped, "
                "not raise: %r" % (e,)
            )

        self.assertEqual(
            len(result), 1,
            "only the published release should be returned, the draft "
            "with a null published_at must be skipped, got: %r" % (result,),
        )
        self.assertEqual(result[0][1], "v1.0.0")


class A4RestartLabelTests(unittest.TestCase):
    def test_A4_restart_event_label_is_coordinator_restart(self):
        with tempfile.TemporaryDirectory() as d:
            raw_dir = os.path.join(d, "raw")
            stats_dir = os.path.join(raw_dir, "stats")
            os.makedirs(stats_dir)
            out_dir = os.path.join(d, "out")
            releases_path = os.path.join(d, "releases.json")
            with open(releases_path, "w") as f:
                json.dump([], f)

            steady = [mk_provider("p%d" % i) for i in range(20)]
            write_json_gz(
                os.path.join(stats_dir, "20260101T120000Z.json.gz"),
                {"providers": steady},
            )
            write_json_gz(
                os.path.join(stats_dir, "20260101T120500Z.json.gz"),
                {"providers": []},  # triggers a restart event
            )
            write_json_gz(
                os.path.join(stats_dir, "20260101T121000Z.json.gz"),
                {"providers": [mk_provider("new%d" % i) for i in range(20)]},
            )

            result = build_report(raw_dir, releases_path, out_dir)

        restart_events = [e for e in result["events"] if e["kind"] == "restart"]
        self.assertEqual(len(restart_events), 1)
        self.assertEqual(
            restart_events[0]["label"], "coordinator restart",
            "restart events must be labelled 'coordinator restart', not "
            "the bare kind name 'restart'",
        )


if __name__ == "__main__":
    unittest.main()
