"""Load recorded provider snapshots from a raw data directory (stats/*.json.gz).

Snapshot time comes from the
filename (YYYYMMDDTHHMMSSZ.json.gz), never the recorded body. Unreadable
files (bad gzip or bad JSON) are skipped and counted rather than raising.
"""
import gzip
import json
import os
import re
import zlib
from datetime import datetime, timezone

_NAME_RE = re.compile(r"^(\d{8}T\d{6})Z\.json\.gz$")

# Only the provider fields the metrics in measure/metrics.py need. Real
# snapshot files carry dozens of extra fields per provider; dropping them
# on load keeps ~1,100 files worth of history well within memory and time
# budget instead of retaining every field.
_NEEDED_PROVIDER_FIELDS = (
    "id",
    "status",
    "runtime_verified",
    "chip",
    "chip_family",
    "memory_gb",
    "gpu_cores",
    "machine_model",
    "requests_served",
    "tokens_generated",
)


def _parse_time(name):
    m = _NAME_RE.match(name)
    if not m:
        return None
    return datetime.strptime(m.group(1), "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)


def _slim_provider(p):
    return dict((k, p.get(k)) for k in _NEEDED_PROVIDER_FIELDS)


def load_stats(raw_dir):
    """Load raw_dir/stats/*.json.gz snapshots.

    Returns (snapshots, skipped):
      snapshots -- time-sorted list of (datetime, providers) tuples, where
        providers is a list of slimmed-down provider dicts.
      skipped -- count of files that could not be read (bad gzip container
        or truncated/invalid JSON body).
    """
    stats_dir = os.path.join(raw_dir, "stats")
    try:
        names = sorted(os.listdir(stats_dir))
    except OSError:
        return [], 0

    snapshots = []
    skipped = 0
    for name in names:
        at = _parse_time(name)
        if at is None:
            continue
        path = os.path.join(stats_dir, name)
        try:
            with gzip.open(path, "rt", encoding="utf-8") as f:
                body = json.load(f)
            providers = [_slim_provider(p) for p in body.get("providers", [])]
        except (OSError, ValueError, EOFError, zlib.error):
            # zlib.error: corrupted compressed bytes inside a valid header.
            # OSError covers a bad gzip container (e.g. bad magic bytes);
            # EOFError covers a gzip container truncated at the byte level
            # (e.g. `head -c N` on a real file), which the gzip module
            # raises directly rather than as an OSError; ValueError covers
            # a bad or truncated JSON body (json.JSONDecodeError is a
            # ValueError subclass, as is UnicodeDecodeError).
            skipped += 1
            continue
        snapshots.append((at, providers))

    snapshots.sort(key=lambda s: s[0])
    return snapshots, skipped
