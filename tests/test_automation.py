"""Tests for the recorder, prune and the GitHub and Vercel config. No network."""
import gzip
import json
import os
import re
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEEP = ["id", "status", "chip", "chip_family", "memory_gb", "gpu_cores",
        "machine_model", "requests_served", "tokens_generated",
        "runtime_verified", "current_model", "trust_level"]
FINAL_RE = re.compile(r"^\d{8}T\d{6}Z\.json\.gz$")
NOW = datetime(2026, 9, 29, 12, 34, 56, tzinfo=timezone.utc)


def _provider(i):
    p = dict((k, "v%d_%s" % (i, k)) for k in KEEP)
    p["id"] = "prov-%d" % i
    p["secret_extra"] = "drop me"
    p["attestation"] = {"blob": "x" * 50}
    return p


def _body(n=2):
    return {"providers": [_provider(i) for i in range(n)], "total": n}


def _opener(status=200, body=None):
    calls = []

    def opener(url, timeout, headers):
        calls.append((url, timeout, headers))
        return status, body
    opener.calls = calls
    return opener


def _stats_files(out):
    d = os.path.join(out, "stats")
    return sorted(os.listdir(d)) if os.path.isdir(d) else []


class A1SnapshotTrims(unittest.TestCase):
    def test_a1_trim_keeps_only_listed_fields(self):
        from record import snapshot
        out = snapshot.trim(_body(3))
        self.assertEqual(list(out.keys()), ["providers"])
        self.assertEqual(len(out["providers"]), 3)
        for p in out["providers"]:
            self.assertTrue(set(p.keys()) <= set(KEEP), p.keys())
            self.assertIn("id", p)
            self.assertNotIn("secret_extra", p)
            self.assertNotIn("attestation", p)

    def test_a1_fetch_and_write_writes_trimmed_named_file_and_loads(self):
        from record import snapshot
        from detect.snapshots import load_stats
        opener = _opener(200, json.dumps(_body(2)).encode())
        with tempfile.TemporaryDirectory() as out:
            path = snapshot.fetch_and_write(out, now=NOW, opener=opener)
            self.assertIsNotNone(path)
            self.assertEqual(os.path.basename(path), "20260929T123456Z.json.gz")
            self.assertEqual(os.path.dirname(os.path.abspath(path)),
                             os.path.abspath(os.path.join(out, "stats")))
            self.assertEqual(_stats_files(out), ["20260929T123456Z.json.gz"])
            with gzip.open(path, "rt", encoding="utf-8") as f:
                written = json.load(f)
            self.assertEqual(list(written.keys()), ["providers"])
            for p in written["providers"]:
                self.assertTrue(set(p.keys()) <= set(KEEP))
                self.assertNotIn("secret_extra", p)
            snaps, skipped = load_stats(out)
            self.assertEqual(skipped, 0)
            self.assertEqual(len(snaps), 1)
            self.assertEqual(snaps[0][0], NOW)
            self.assertEqual([p["id"] for p in snaps[0][1]], ["prov-0", "prov-1"])

    def test_a1_request_uses_stats_url_timeout_and_wilt_user_agent(self):
        from record import snapshot
        opener = _opener(200, json.dumps(_body(1)).encode())
        with tempfile.TemporaryDirectory() as out:
            snapshot.fetch_and_write(out, now=NOW, opener=opener)
        self.assertEqual(len(opener.calls), 1)
        url, timeout, headers = opener.calls[0]
        self.assertEqual(url, "https://api.darkbloom.dev/v1/stats")
        self.assertEqual(timeout, 45)
        ua = dict((k.lower(), v) for k, v in dict(headers).items()).get("user-agent", "")
        self.assertIn("wilt", ua.lower())


class A2SnapshotRejects(unittest.TestCase):
    def _assert_rejected(self, status, body):
        from record import snapshot
        with tempfile.TemporaryDirectory() as out:
            path = snapshot.fetch_and_write(out, now=NOW, opener=_opener(status, body))
            self.assertIsNone(path)
            self.assertEqual(_stats_files(out), [])

    def test_a2_non_200(self):
        self._assert_rejected(503, json.dumps(_body(1)).encode())

    def test_a2_non_json(self):
        self._assert_rejected(200, b"<html>not json</html>")

    def test_a2_no_providers_key(self):
        self._assert_rejected(200, json.dumps({"total": 0}).encode())

    def test_a2_providers_not_a_list(self):
        self._assert_rejected(200, json.dumps({"providers": "nope"}).encode())

    def test_a2_main_exits_nonzero_and_writes_nothing(self):
        from record import snapshot
        with tempfile.TemporaryDirectory() as out:
            with mock.patch.object(snapshot, "fetch_and_write", return_value=None):
                rc = snapshot.main(["--out", out])
            self.assertNotEqual(rc, 0)
            self.assertEqual(_stats_files(out), [])

    def test_a2_main_exits_zero_on_success(self):
        from record import snapshot
        with tempfile.TemporaryDirectory() as out:
            with mock.patch.object(snapshot, "fetch_and_write", return_value="/x/y.json.gz"):
                rc = snapshot.main(["--out", out])
            self.assertEqual(rc, 0)


class A3InterruptedWrite(unittest.TestCase):
    def test_a3_failure_during_gzip_write_leaves_no_final_file(self):
        from record import snapshot
        real_open = gzip.open

        def boom(*args, **kwargs):
            f = real_open(*args, **kwargs)
            try:
                f.write(b'{"providers": [')
            finally:
                f.close()
            raise OSError("simulated disk failure")

        opener = _opener(200, json.dumps(_body(2)).encode())
        with tempfile.TemporaryDirectory() as out:
            with mock.patch("gzip.open", side_effect=boom):
                try:
                    result = snapshot.fetch_and_write(out, now=NOW, opener=opener)
                except OSError:
                    result = None
            self.assertIsNone(result)
            finals = [n for n in _stats_files(out) if FINAL_RE.match(n)]
            self.assertEqual(finals, [])

    def test_a3_failure_during_rename_leaves_no_final_file(self):
        from record import snapshot
        opener = _opener(200, json.dumps(_body(2)).encode())
        with tempfile.TemporaryDirectory() as out:
            with mock.patch("os.replace", side_effect=OSError("boom")), \
                    mock.patch("os.rename", side_effect=OSError("boom")):
                try:
                    snapshot.fetch_and_write(out, now=NOW, opener=opener)
                except OSError:
                    pass
            finals = [n for n in _stats_files(out) if FINAL_RE.match(n)]
            self.assertEqual(finals, [])


class A4Prune(unittest.TestCase):
    @staticmethod
    def _name(dt):
        return dt.strftime("%Y%m%dT%H%M%SZ.json.gz")

    def test_a4_removes_only_files_older_than_days(self):
        from record import prune
        with tempfile.TemporaryDirectory() as out:
            d = os.path.join(out, "stats")
            os.makedirs(d)
            old = self._name(NOW - timedelta(days=20))
            mid = self._name(NOW - timedelta(days=13))
            new = self._name(NOW - timedelta(days=1))
            junk = "notes.json.gz"
            for n in (old, mid, new, junk):
                with open(os.path.join(d, n), "wb") as f:
                    f.write(b"x")
            removed = prune.prune(out, days=14, now=NOW)
            self.assertEqual([os.path.basename(p) for p in removed], [old])
            self.assertEqual(sorted(os.listdir(d)), sorted([mid, new, junk]))

    def test_a4_default_days_is_14(self):
        from record import prune
        with tempfile.TemporaryDirectory() as out:
            d = os.path.join(out, "stats")
            os.makedirs(d)
            old = self._name(NOW - timedelta(days=15))
            keep = self._name(NOW - timedelta(days=13))
            for n in (old, keep):
                open(os.path.join(d, n), "wb").close()
            removed = prune.prune(out, now=NOW)
            self.assertEqual([os.path.basename(p) for p in removed], [old])

    def test_a4_main_returns_zero(self):
        from record import prune
        with tempfile.TemporaryDirectory() as out:
            os.makedirs(os.path.join(out, "stats"))
            self.assertEqual(prune.main(["--out", out]), 0)


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


class A5Workflows(unittest.TestCase):
    RECORD = ".github/workflows/record.yml"
    PUBLISH = ".github/workflows/publish.yml"
    HOURLY = re.compile(r"cron: *['\"]\d{1,2} \* \* \* \*['\"]")

    def _assert_no_foreign_secrets(self, text):
        refs = re.findall(r"secrets\.([A-Za-z0-9_]+)", text)
        for r in refs:
            self.assertEqual(r, "GITHUB_TOKEN")

    def _yaml_parses_if_available(self, rel):
        try:
            import yaml
        except ImportError:
            import shutil
            import subprocess
            exe = shutil.which("actionlint")
            if exe is None:
                self.fail("cannot validate %s: neither PyYAML nor actionlint is available" % rel)
            r = subprocess.run([exe, os.path.join(ROOT, rel)],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            return
        doc = yaml.safe_load(_read(rel))
        self.assertIsInstance(doc, dict)
        # PyYAML reads the bare key `on` as True.
        self.assertTrue("on" in doc or True in doc)
        self.assertIn("jobs", doc)

    def test_a5_record_workflow(self):
        t = _read(self.RECORD)
        self.assertIn("*/10 * * * *", t)
        self.assertIn("workflow_dispatch", t)
        self.assertIn("concurrency", t)
        self.assertRegex(t, r"cancel-in-progress: *false")
        self._assert_no_foreign_secrets(t)
        self._yaml_parses_if_available(self.RECORD)

    def test_a5_publish_workflow(self):
        t = _read(self.PUBLISH)
        self.assertRegex(t, self.HOURLY)
        self.assertIn("workflow_dispatch", t)
        self.assertIn("contents: write", t)
        self._assert_no_foreign_secrets(t)
        self._yaml_parses_if_available(self.PUBLISH)


class A6Vercel(unittest.TestCase):
    def test_a6_vercel_json(self):
        with open(os.path.join(ROOT, "vercel.json"), encoding="utf-8") as f:
            cfg = json.load(f)
        self.assertEqual(cfg.get("outputDirectory"), "site")
        self.assertFalse(cfg.get("buildCommand"), "no build step expected")
        self.assertIs(cfg["git"]["deploymentEnabled"]["data"], False)


if __name__ == "__main__":
    unittest.main()
