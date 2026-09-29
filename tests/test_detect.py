"""Failing-first tests for detect/snapshots.py and detect/events.py.

Covers:
  T1 - restart event fires at the empty snapshot, consecutive qualifying
       snapshots within 10 min merge into one event
  T2 - gradual 5%-per-snapshot churn never trips the restart rule
  T6 - find_releases returns only releases whose published_at falls inside
       the [start, end] span
  T7 - load_stats skips an unreadable (truncated) file and still succeeds
"""
import gzip
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from detect.events import find_releases, find_restarts
from detect.snapshots import load_stats


def mk_provider(pid, status="serving", runtime_verified=True,
                 chip="Apple M3 Ultra", chip_family="M3", memory_gb=64,
                 gpu_cores=32, machine_model="Mac15,14",
                 requests_served=1000, tokens_generated=500000,
                 current_model="gpt-oss-20b", trust_level="hardware"):
    return {
        "id": pid,
        "status": status,
        "runtime_verified": runtime_verified,
        "chip": chip,
        "chip_family": chip_family,
        "memory_gb": memory_gb,
        "gpu_cores": gpu_cores,
        "machine_model": machine_model,
        "requests_served": requests_served,
        "tokens_generated": tokens_generated,
        "current_model": current_model,
        "trust_level": trust_level,
    }


def write_json_gz(path, obj):
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(obj, f)


def write_truncated_json_gz(path, obj):
    """Write a *complete*, valid gzip stream whose JSON payload was cut off
    mid-write -- this is the exact failure mode observed in the real
    recorded snapshots (a well-formed gzip footer around truncated JSON
    text), not a truncated gzip container."""
    full_text = json.dumps(obj)
    truncated_text = full_text[: len(full_text) // 2]
    with gzip.open(path, "wt", encoding="utf-8") as f:
        f.write(truncated_text)


class FindRestartsTests(unittest.TestCase):
    def test_T1_restart_event_at_empty_snapshot(self):
        base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        steady = [mk_provider("p%d" % i) for i in range(100)]
        t0 = base
        t1 = base + timedelta(minutes=5)   # empty snapshot -> restart trigger
        t2 = base + timedelta(minutes=10)  # all-new ids, within 10 min of t1
        new_ids = [mk_provider("new%d" % i) for i in range(100)]

        snapshots = [
            (t0, steady),
            (t1, []),
            (t2, new_ids),
        ]

        restarts = find_restarts(snapshots)

        self.assertEqual(
            restarts, [t1],
            "expected exactly one restart event at the empty snapshot's "
            "time, with the following all-new-ids snapshot merged into it "
            "because it is within 10 minutes",
        )

    def test_T2_gradual_five_percent_churn_no_restart(self):
        base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        ids = list(range(100))
        snapshots = []
        next_id = 100
        for i in range(10):
            t = base + timedelta(minutes=5 * i)
            providers = [mk_provider("p%d" % j) for j in ids]
            snapshots.append((t, providers))
            # replace 5% (5 of 100) of ids before the next snapshot
            ids = ids[5:] + list(range(next_id, next_id + 5))
            next_id += 5

        restarts = find_restarts(snapshots)

        self.assertEqual(
            restarts, [],
            "5%% churn per snapshot keeps overlap at 95%%, well above the "
            "50%% restart threshold, so no restart should be detected",
        )


class FindReleasesTests(unittest.TestCase):
    def test_T6_only_release_inside_span_is_returned(self):
        start = datetime(2026, 9, 1, 0, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 9, 30, 0, 0, 0, tzinfo=timezone.utc)
        releases = [
            {"tag": "v1.0.0", "published_at": "2026-09-15T12:00:00Z"},  # inside
            {"tag": "v0.9.0", "published_at": "2026-08-01T00:00:00Z"},  # before start
            {"tag": "v1.1.0", "published_at": "2026-10-05T00:00:00Z"},  # after end
        ]

        result = find_releases(releases, start, end)

        self.assertEqual(
            len(result), 1,
            "expected exactly one release event inside [start, end], got: %r"
            % (result,),
        )
        at, tag = result[0]
        self.assertEqual(tag, "v1.0.0")
        self.assertEqual(at, datetime(2026, 9, 15, 12, 0, 0, tzinfo=timezone.utc))


class LoadStatsTests(unittest.TestCase):
    def test_T7_truncated_file_is_skipped_and_run_succeeds(self):
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
            write_truncated_json_gz(
                os.path.join(stats_dir, "20260928T060400Z.json.gz"),
                {"providers": [mk_provider("d%d" % i) for i in range(50)]},
            )

            snapshots, skipped = load_stats(d)

        self.assertEqual(
            skipped, 1,
            "exactly one truncated file among three should be counted as skipped",
        )
        self.assertEqual(
            len(snapshots), 2,
            "the two valid snapshots should still load",
        )
        times = [t for t, _ in snapshots]
        self.assertEqual(times, sorted(times), "snapshots must be time-sorted")
        counts = sorted(len(providers) for _, providers in snapshots)
        self.assertEqual(counts, [1, 2])


if __name__ == "__main__":
    unittest.main()
