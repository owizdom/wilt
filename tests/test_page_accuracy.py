"""Accuracy fixes: gaps for empty snapshots and observed-only numbers."""
import unittest
from datetime import datetime, timedelta

from report.timeline import build_timeline


def _p(pid, served):
    return {"id": pid, "status": "online", "runtime_verified": True,
            "requests_served": served, "chip_family": "M1"}


class EmptySnapshotGap(unittest.TestCase):
    def test_empty_snapshot_has_null_rpm_and_stuck_and_zero_macs(self):
        t0 = datetime(2026, 1, 1, 12, 0, 0)
        snaps = [
            (t0, [_p("a", 100), _p("b", 200)]),
            (t0 + timedelta(minutes=5), [_p("a", 150), _p("b", 260)]),
            (t0 + timedelta(minutes=10), []),
            (t0 + timedelta(minutes=15), [_p("c", 5)]),
        ]
        tl = build_timeline(snaps)
        self.assertIsNotNone(tl[1]["rpm"])
        self.assertEqual(tl[2]["macs"], 0)
        self.assertIsNone(tl[2]["rpm"])
        self.assertIsNone(tl[2]["stuck"])
        self.assertIsNone(tl[3]["rpm"])
        self.assertEqual(tl[3]["stuck"], 0)


class PageWording(unittest.TestCase):
    def setUp(self):
        import report.page as page
        with open(page.__file__) as f:
            self.src = f.read()

    def test_no_interpolated_macs_and_labels(self):
        self.assertNotIn("macs: lerp(", self.src)
        self.assertIn("Baseline (median)", self.src)
        self.assertIn("stuck before, ", self.src)
        self.assertLess(self.src.index("stuck before, "),
                        self.src.index("' after.'"))


if __name__ == "__main__":
    unittest.main()
