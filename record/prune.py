"""Delete snapshots older than N days, judged by the time in the filename."""
import argparse
import os
import re
import sys
from datetime import datetime, timedelta, timezone


_NAME_RE = re.compile(r"^(\d{8}T\d{6})Z\.json\.gz$")


def _parse(name):
    m = _NAME_RE.fullmatch(name)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def prune(out_dir, days=14, now=None):
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    stats_dir = os.path.join(out_dir, "stats")
    try:
        names = sorted(os.listdir(stats_dir))
    except OSError:
        return []
    removed = []
    for name in names:
        at = _parse(name)
        if at is None or at >= cutoff:
            continue
        path = os.path.join(stats_dir, name)
        os.remove(path)
        removed.append(path)
    return removed


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True)
    ap.add_argument("--days", type=int, default=14)
    args = ap.parse_args(argv)
    for p in prune(args.out, days=args.days):
        print("removed", p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
