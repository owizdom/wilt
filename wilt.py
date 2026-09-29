#!/usr/bin/env python3
"""CLI entry point for wilt.

Usage:
    python3 wilt.py --raw DIR --releases FILE --out DIR
"""
import argparse
import sys

from report.write import build_report


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Score Darkbloom coordinator deploys and provider releases "
            "from recorded public snapshots."
        )
    )
    parser.add_argument(
        "--raw", required=True,
        help="raw data directory (stats/*.json.gz), for example ./data/raw",
    )
    parser.add_argument(
        "--releases", required=True,
        help="releases JSON file ([{\"tag\", \"published_at\"}])",
    )
    parser.add_argument(
        "--out", required=True,
        help="output directory for events.json, EVENTS.md and index.html",
    )
    parser.add_argument(
        "--history", default=None,
        help="permanent event log (JSONL) to merge into and rewrite",
    )
    args = parser.parse_args(argv)

    result = build_report(args.raw, args.releases, args.out,
                          history_path=args.history)

    restarts = sum(1 for e in result["events"] if e.get("kind") == "restart")
    releases = sum(1 for e in result["events"] if e.get("kind") == "release")
    print(
        "%d events (%d restarts, %d releases), %d files skipped, wrote "
        "%s/events.json, %s/EVENTS.md and %s/index.html"
        % (
            len(result["events"]), restarts, releases, result["skipped_files"],
            args.out, args.out, args.out,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
