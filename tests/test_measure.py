"""Failing-first tests for measure/metrics.py.

Covers:
  T3 - drop and recovery_minutes off a synthetic 100 -> 0 -> 50 -> 96 series
  T4 - stuck_before / stuck_after / stuck_carried, with carry-matching keyed
       on hardware + counter identity (not id, which changes across a
       restart) and non-zero requests_served required to count as carried
  T5 - a 0 -> 62,912 counter "restore" is excluded from requests_per_min
"""
import unittest
from datetime import datetime, timedelta, timezone

from measure.metrics import measure_event


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


class MeasureEventDropRecoveryTests(unittest.TestCase):
    def test_T3_drop_and_recovery_minutes(self):
        at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        def fleet(n, prefix):
            return [mk_provider("%s-%d" % (prefix, i)) for i in range(n)]

        snapshots = [
            (at - timedelta(minutes=20), fleet(100, "b1")),
            (at - timedelta(minutes=10), fleet(100, "b2")),
            (at, fleet(0, "x")),
            (at + timedelta(minutes=5), fleet(50, "r1")),
            (at + timedelta(minutes=15), fleet(96, "r2")),  # >= 95% of 100
            (at + timedelta(minutes=30), fleet(100, "r3")),
        ]

        result = measure_event(snapshots, at)

        self.assertEqual(result["baseline_macs"], 100)
        self.assertEqual(result["min_macs_after"], 0)
        self.assertEqual(result["drop"], 100)
        self.assertEqual(
            result["recovery_minutes"], 15,
            "recovery_minutes must be the time to the first snapshot at or "
            "above 95%% of baseline (the 96-provider snapshot at +15 min), "
            "not the 50-provider snapshot at +5 min",
        )


class MeasureEventStuckTests(unittest.TestCase):
    def test_T4_stuck_before_after_carried_excludes_zero_counter_matches(self):
        at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        before_time = at - timedelta(minutes=10)
        after_time = at + timedelta(minutes=60)

        # A: stuck before and after; ids differ (restarts hand out new ids)
        # but hardware + non-zero counters match -> carried.
        a_before = mk_provider(
            "A-before", status="online", runtime_verified=False,
            chip="Apple M3 Ultra", chip_family="M3", memory_gb=256,
            gpu_cores=80, machine_model="Mac15,14",
            requests_served=500, tokens_generated=900000,
        )
        a_after = mk_provider(
            "A-after", status="online", runtime_verified=False,
            chip="Apple M3 Ultra", chip_family="M3", memory_gb=256,
            gpu_cores=80, machine_model="Mac15,14",
            requests_served=500, tokens_generated=900000,
        )

        # B: stuck before and after, identical fields, but both counters are
        # zero -> matches on identity yet must NOT count as carried.
        b_before = mk_provider(
            "B-before", status="serving", runtime_verified=False,
            chip="Apple M2", chip_family="M2", memory_gb=64,
            gpu_cores=30, machine_model="Mac14,2",
            requests_served=0, tokens_generated=0,
        )
        b_after = mk_provider(
            "B-after", status="serving", runtime_verified=False,
            chip="Apple M2", chip_family="M2", memory_gb=64,
            gpu_cores=30, machine_model="Mac14,2",
            requests_served=0, tokens_generated=0,
        )

        # C: stuck before, recovered by the +60 min snapshot.
        c_before = mk_provider(
            "C-before", status="online", runtime_verified=False,
            chip="Apple M1", chip_family="M1", memory_gb=16,
            gpu_cores=8, machine_model="Mac14,7",
            requests_served=200, tokens_generated=40000,
        )
        c_after = mk_provider(
            "C-after", status="serving", runtime_verified=True,
            chip="Apple M1", chip_family="M1", memory_gb=16,
            gpu_cores=8, machine_model="Mac14,7",
            requests_served=250, tokens_generated=48000,
        )

        # D: newly stuck after the event, no match in the before snapshot.
        d_after = mk_provider(
            "D-after", status="online", runtime_verified=False,
            chip="Apple M4", chip_family="M4", memory_gb=128,
            gpu_cores=40, machine_model="Mac16,1",
            requests_served=999, tokens_generated=123456,
        )

        # E: healthy filler present at both times, never stuck.
        e_before = mk_provider("E-before", status="serving", runtime_verified=True)
        e_after = mk_provider("E-after", status="serving", runtime_verified=True)

        snapshots = [
            (before_time, [a_before, b_before, c_before, e_before]),
            (after_time, [a_after, b_after, d_after, c_after, e_after]),
        ]

        result = measure_event(snapshots, at)

        self.assertEqual(result["stuck_before"], 3, "A, B, C are stuck before")
        self.assertEqual(
            result["stuck_after"], 3,
            "A, B, D are stuck after (C recovered, so it drops out)",
        )
        self.assertEqual(
            result["stuck_carried"], 1,
            "only A matches on hardware+counters with a non-zero "
            "requests_served; B matches every field but both counters are "
            "zero and must be excluded",
        )
        self.assertEqual(
            result["stuck_by_chip"], {"M3": 1, "M2": 1, "M4": 1},
            "stuck_by_chip must group the stuck-after providers (A, B, D) "
            "by chip_family",
        )


class MeasureEventRequestRateTests(unittest.TestCase):
    def test_T5_counter_restore_excluded_from_requests_per_min(self):
        at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        before1_time = at - timedelta(minutes=10)
        before2_time = at - timedelta(minutes=5)
        after1_time = at + timedelta(minutes=5)
        after2_time = at + timedelta(minutes=15)

        before1 = mk_provider("const", requests_served=1000)
        before2 = mk_provider("const", requests_served=1150)  # +150 / 5 min = 30/min

        # P's counter goes 0 -> 62,912 in one interval: previous counter is
        # 0 and the delta is far past the 5,000 restore-guard threshold, so
        # it must be dropped entirely rather than counted as work.
        p_restore_1 = mk_provider("P", requests_served=0)
        p_restore_2 = mk_provider("P", requests_served=62912)

        # Q is normal traffic in the same interval, to prove the exclusion
        # is selective and not just "no rate after the event".
        q_normal_1 = mk_provider("Q", requests_served=500)
        q_normal_2 = mk_provider("Q", requests_served=800)  # +300 / 10 min = 30/min

        snapshots = [
            (before1_time, [before1]),
            (before2_time, [before2]),
            (after1_time, [p_restore_1, q_normal_1]),
            (after2_time, [p_restore_2, q_normal_2]),
        ]

        result = measure_event(snapshots, at)

        self.assertAlmostEqual(
            result["requests_per_min_before"], 30.0, places=3,
        )
        self.assertAlmostEqual(
            result["requests_per_min_after"], 30.0, places=3,
            msg=(
                "the 62,912 restore delta on P must be excluded; if it "
                "were included the rate would be roughly 6,321/min instead "
                "of Q's real 30/min"
            ),
        )


if __name__ == "__main__":
    unittest.main()
