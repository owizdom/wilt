"""Fetch the public Darkbloom stats once and write a trimmed gzip snapshot."""
import argparse
import gzip
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

URL = "https://api.darkbloom.dev/v1/stats"
TIMEOUT = 45
HEADERS = {"User-Agent": "wilt-recorder/1 (+https://github.com/owizdom/wilt)"}
KEEP = ["id", "status", "chip", "chip_family", "memory_gb", "gpu_cores",
        "machine_model", "requests_served", "tokens_generated",
        "runtime_verified", "current_model", "trust_level"]


def default_opener(url, timeout, headers):
    req = urllib.request.Request(url, headers=dict(headers))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, b""


def trim(body):
    out = []
    for p in body["providers"]:
        if isinstance(p, dict):
            out.append(dict((k, p[k]) for k in KEEP if k in p))
    return {"providers": out}


def fetch_and_write(out_dir, now=None, opener=None):
    """Return the written path, or None when the response is unusable."""
    opener = opener or default_opener
    now = now or datetime.now(timezone.utc)
    try:
        status, data = opener(URL, TIMEOUT, HEADERS)
    except Exception as e:  # network errors, timeouts
        sys.stderr.write("fetch failed: %s\n" % e)
        return None
    if status != 200:
        sys.stderr.write("unexpected HTTP status %s\n" % status)
        return None
    try:
        body = json.loads(data)
    except (ValueError, TypeError):
        sys.stderr.write("response is not JSON\n")
        return None
    if not isinstance(body, dict) or not isinstance(body.get("providers"), list):
        sys.stderr.write("response has no providers list\n")
        return None
    trimmed = trim(body)

    stats_dir = os.path.join(out_dir, "stats")
    os.makedirs(stats_dir, exist_ok=True)
    name = now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ.json.gz")
    final = os.path.join(stats_dir, name)
    tmp = final + ".tmp"
    try:
        payload = json.dumps(trimmed, separators=(",", ":")).encode("utf-8")
        with gzip.open(tmp, "wb") as f:
            f.write(payload)
        os.replace(tmp, final)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    return final


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    path = fetch_and_write(args.out)
    if path is None:
        return 1
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
