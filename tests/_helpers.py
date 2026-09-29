"""Shared test-only helpers. Not a test module itself (unittest discover's
default "test*.py" pattern does not match this filename, so it is never
collected as a suite on its own).
"""
import gzip
import json
import re
from datetime import datetime, timezone


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


def iso_utc(dt):
    """Match report/write.py's _iso: "%Y-%m-%dT%H:%M:%SZ"."""
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


_ISO_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})")


def parse_iso_utc(s):
    m = _ISO_RE.match(s)
    if not m:
        raise ValueError("not an ISO UTC timestamp: %r" % (s,))
    y, mo, d, h, mi, se = (int(x) for x in m.groups())
    return datetime(y, mo, d, h, mi, se, tzinfo=timezone.utc)


_EMBEDDED_JSON_RE = re.compile(
    r'<script type="application/json" id="wilt-data">(.*?)</script>',
    re.S,
)


def extract_embedded_json(html):
    """Pull the JSON payload out of the
    <script type="application/json" id="wilt-data">...</script>
    block report/page.py must embed, and parse it. Raises AssertionError
    with a clear message if the block is missing, rather than a bare
    AttributeError on None, so a failing test says why.
    """
    m = _EMBEDDED_JSON_RE.search(html)
    if not m:
        raise AssertionError(
            "no <script type=\"application/json\" id=\"wilt-data\"> "
            "block found in the rendered page"
        )
    return json.loads(m.group(1))
