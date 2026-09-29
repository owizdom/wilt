import os
import tempfile
import unittest
from datetime import datetime, timezone

from record import prune


class PruneExactName(unittest.TestCase):
    def test_loose_names_never_deleted(self):
        now = datetime(2026, 9, 29, tzinfo=timezone.utc)
        loose = ["2026928T1234Z.json.gz", "20260101T000000Z.json.gz.bak",
                 "x20260101T000000Z.json.gz", "20260101T000000Z.json.gz\n"]
        with tempfile.TemporaryDirectory() as out:
            d = os.path.join(out, "stats")
            os.makedirs(d)
            for n in loose + ["20260101T000000Z.json.gz"]:
                open(os.path.join(d, n.strip("\n") if "\n" in n else n), "wb").close()
            removed = prune.prune(out, now=now)
            self.assertEqual([os.path.basename(p) for p in removed],
                             ["20260101T000000Z.json.gz"])
            self.assertIn("2026928T1234Z.json.gz", os.listdir(d))
        self.assertIsNone(prune._parse("20260101T000000Z.json.gz\n"))
        # Loose names a plain strptime would accept must not parse at all.
        self.assertIsNone(prune._parse("2026928T1234Z.json.gz"))
        self.assertIsNone(prune._parse("202611T1234Z.json.gz"))


if __name__ == "__main__":
    unittest.main()
