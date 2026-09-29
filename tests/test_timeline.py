"""Failing-first tests for report/timeline.py.

Covers:
  U1 - build_timeline(snapshots) -> one entry per readable snapshot with
       correct macs, stuck and rpm (restore-guard delta excluded, rpm null
       for the first snapshot and for the snapshot right after an empty
       one).
  U2 - event_window(snapshots, at) -> "window" spans at-30min to at+3h
       clipped to the data, computed with the same per-entry rpm rule as
       build_timeline (i.e. it reuses the full snapshot history for its
       deltas, not just the entries inside the window -- see "decided" in
       the handback report); "chips_before" counts the last snapshot
       strictly before at.
"""
import unittest
from datetime import datetime, timedelta, timezone

from report.timeline import build_timeline, event_window

from tests._helpers import iso_utc, mk_provider


class BuildTimelineTests(unittest.TestCase):
    def test_U1_macs_stuck_rpm_with_restore_guard_and_empty_snapshot_nulls(self):
        base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        t0 = base
        t1 = base + timedelta(minutes=5)
        t2 = base + timedelta(minutes=10)  # empty: a restart
        t3 = base + timedelta(minutes=15)  # right after the empty snapshot
        t4 = base + timedelta(minutes=20)

        # t0: two healthy providers, first entry overall -> rpm must be None.
        snap0 = [
            mk_provider("A", requests_served=1000),
            mk_provider("B", requests_served=2000),
        ]
        # t1: normal traffic on both -> rpm = (50 + 60) / 5 = 22.0
        snap1 = [
            mk_provider("A", requests_served=1050),
            mk_provider("B", requests_served=2060),
        ]
        # t2: empty snapshot (a restart) -> macs 0; no provider is observed,
        # so stuck and rpm are None (a gap, not a measured zero).
        snap2 = []
        # t3: brand new ids after the restart, plus one stuck provider F.
        # This entry immediately follows an empty snapshot, so rpm must be
        # forced to None even though the formula alone (no overlapping ids
        # with t2) would also compute 0.0 -- the explicit "after an empty
        # one" rule must still apply.
        snap3 = [
            mk_provider("C", requests_served=500),
            mk_provider("D", requests_served=800),
            mk_provider("E", requests_served=0),
            mk_provider(
                "F", status="online", runtime_verified=False, requests_served=10,
            ),
        ]
        # t4: C and D take normal deltas; E goes 0 -> 6000, which is a
        # restore (prev counter 0, delta > 5000) and must be dropped; F
        # (still stuck) takes a normal delta.
        # rpm = (60 + 30 + 5) / 5 = 19.0
        snap4 = [
            mk_provider("C", requests_served=560),
            mk_provider("D", requests_served=830),
            mk_provider("E", requests_served=6000),
            mk_provider(
                "F", status="online", runtime_verified=False, requests_served=15,
            ),
        ]

        snapshots = [
            (t0, snap0),
            (t1, snap1),
            (t2, snap2),
            (t3, snap3),
            (t4, snap4),
        ]

        timeline = build_timeline(snapshots)

        expected = [
            {"t": iso_utc(t0), "macs": 2, "stuck": 0, "rpm": None},
            {"t": iso_utc(t1), "macs": 2, "stuck": 0, "rpm": 22.0},
            {"t": iso_utc(t2), "macs": 0, "stuck": None, "rpm": None},
            {"t": iso_utc(t3), "macs": 4, "stuck": 1, "rpm": None},
            {"t": iso_utc(t4), "macs": 4, "stuck": 1, "rpm": 19.0},
        ]

        self.assertEqual(len(timeline), 5, "one entry per readable snapshot")
        for i, (got, want) in enumerate(zip(timeline, expected)):
            self.assertEqual(got["t"], want["t"], "entry %d: t" % i)
            self.assertEqual(got["macs"], want["macs"], "entry %d: macs" % i)
            self.assertEqual(got["stuck"], want["stuck"], "entry %d: stuck" % i)
            if want["rpm"] is None:
                self.assertIsNone(
                    got["rpm"],
                    "entry %d: rpm must be None (first snapshot or right "
                    "after an empty one)" % i,
                )
            else:
                self.assertIsNotNone(got["rpm"], "entry %d: rpm" % i)
                self.assertAlmostEqual(got["rpm"], want["rpm"], places=6,
                                        msg="entry %d: rpm" % i)


class EventWindowTests(unittest.TestCase):
    def test_U2_window_clips_to_at_minus_30_to_at_plus_3h_and_chips_before(self):
        base = datetime(2026, 2, 1, 0, 0, 0, tzinfo=timezone.utc)
        at = base + timedelta(minutes=70)
        window_start = at - timedelta(minutes=30)  # base + 40 min
        window_end = at + timedelta(hours=3)        # base + 250 min

        s0_t = base                                   # before window_start -> excluded
        s1_t = base + timedelta(minutes=40)            # == window_start -> included
        s2_t = at                                      # == at -> included
        s3_t = base + timedelta(minutes=130)            # inside window -> included
        s4_t = base + timedelta(minutes=260)            # after window_end -> excluded

        s0 = [
            mk_provider("p1", chip_family="M3", requests_served=100),
            mk_provider("p2", chip_family="M3", requests_served=200),
        ]
        # last snapshot strictly before `at`: 3 M3 + 1 M2 -> chips_before.
        s1 = [
            mk_provider("p1", chip_family="M3", requests_served=130),
            mk_provider("p2", chip_family="M3", requests_served=250),
            mk_provider("q1", chip_family="M3", requests_served=10),
            mk_provider("q2", chip_family="M2", requests_served=20),
        ]
        # the event itself: all-new ids, a different chip family that must
        # NOT leak into chips_before (chips_before uses the snapshot
        # strictly before `at`, not the one at `at`).
        s2 = [
            mk_provider("z1", chip_family="M4", requests_served=500),
            mk_provider("z2", chip_family="M4", requests_served=500),
        ]
        s3 = [
            mk_provider("z1", chip_family="M4", requests_served=560),
            mk_provider("w1", chip_family="M3", requests_served=1),
            mk_provider("w2", chip_family="M3", requests_served=1),
            mk_provider("w3", chip_family="M3", requests_served=1),
            mk_provider("w4", chip_family="M3", requests_served=1),
            mk_provider("w5", chip_family="M3", requests_served=1),
        ]
        s4 = [mk_provider("v1")]

        snapshots = [
            (s0_t, s0), (s1_t, s1), (s2_t, s2), (s3_t, s3), (s4_t, s4),
        ]

        result = event_window(snapshots, at)

        self.assertIn("window", result)
        self.assertIn("chips_before", result)

        window = result["window"]
        got_times = [e["t"] for e in window]
        expected_times = [iso_utc(s1_t), iso_utc(s2_t), iso_utc(s3_t)]
        self.assertEqual(
            got_times, expected_times,
            "window must contain exactly the snapshots with "
            "at-30min <= t <= at+3h, clipped to the data (s0 excluded as "
            "before window_start, s4 excluded as after window_end)",
        )

        macs_by_time = dict((e["t"], e["macs"]) for e in window)
        self.assertEqual(macs_by_time[iso_utc(s1_t)], 4)
        self.assertEqual(macs_by_time[iso_utc(s2_t)], 2)
        self.assertEqual(macs_by_time[iso_utc(s3_t)], 6)

        # rpm inside the window must come from the same consecutive-pair
        # computation as build_timeline over the full snapshot history,
        # not be reset to None just because a snapshot is the first one
        # inside the window: s1's rpm is derived from s0, which is itself
        # outside the window.
        rpm_by_time = dict((e["t"], e["rpm"]) for e in window)
        self.assertAlmostEqual(
            rpm_by_time[iso_utc(s1_t)], 2.0, places=6,
            msg="s1 rpm = ((130-100)+(250-200)) / 40 minutes = 2.0, using "
                "s0 (outside the window) as the previous snapshot",
        )
        self.assertIsNone(rpm_by_time[iso_utc(s2_t)])  # no shared ids: no measurement
        self.assertAlmostEqual(rpm_by_time[iso_utc(s3_t)], 1.0, places=6)

        self.assertEqual(
            result["chips_before"], {"M3": 3, "M2": 1},
            "chips_before must count the last snapshot strictly before "
            "`at` (s1), not the snapshot at `at` itself (s2, all M4)",
        )


if __name__ == "__main__":
    unittest.main()
