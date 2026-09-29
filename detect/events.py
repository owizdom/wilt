"""Restart and release event detection.
"""
from datetime import datetime, timedelta, timezone

RESTART_MERGE_WINDOW = timedelta(minutes=10)
RESTART_OVERLAP_THRESHOLD = 0.5


def _qualifies(prev_providers, cur_providers):
    """A snapshot qualifies as a restart trigger when it has 0 providers, or
    when fewer than 50% of its provider ids appear in the previous readable
    snapshot."""
    if not cur_providers:
        return True
    prev_ids = set(p["id"] for p in prev_providers)
    cur_ids = [p["id"] for p in cur_providers]
    matched = sum(1 for pid in cur_ids if pid in prev_ids)
    fraction = matched / len(cur_ids)
    return fraction < RESTART_OVERLAP_THRESHOLD


def find_restarts(snapshots):
    """snapshots: time-sorted list of (datetime, providers).

    Returns a list of restart event datetimes. Consecutive qualifying
    snapshots within 10 minutes of the previous qualifying snapshot merge
    into a single event at the first qualifying snapshot's time.
    """
    if not snapshots:
        return []

    restarts = []
    last_qualifying_time = None

    # An empty snapshot qualifies as a restart trigger on its own, even
    # when it is the very first snapshot in the recording and so has no
    # previous snapshot to compare against.
    first_time, first_providers = snapshots[0]
    if not first_providers:
        restarts.append(first_time)
        last_qualifying_time = first_time

    for i in range(1, len(snapshots)):
        _, prev_providers = snapshots[i - 1]
        cur_time, cur_providers = snapshots[i]
        if not _qualifies(prev_providers, cur_providers):
            continue
        if last_qualifying_time is None or (cur_time - last_qualifying_time) > RESTART_MERGE_WINDOW:
            restarts.append(cur_time)
        last_qualifying_time = cur_time
    return restarts


def _parse_iso_utc(s):
    # datetime.fromisoformat only gained "Z" support in Python 3.11; convert
    # to an explicit offset so this works on 3.9 too.
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def find_releases(releases, start, end):
    """releases: list of release dicts, either the "tag" shape already used
    by tests/fixtures/releases.json or the raw `gh api
    repos/OWNER/REPO/releases` shape (keyed "tag_name"). start/end: UTC
    datetimes bounding the recorded span.

    Returns [(published_at, tag), ...] for releases whose published_at
    falls inside [start, end] (inclusive), sorted chronologically. Entries
    with a null published_at (unpublished drafts) are skipped.
    """
    out = []
    for r in releases:
        published_at = r.get("published_at")
        if published_at is None:
            continue
        tag = r.get("tag", r.get("tag_name"))
        at = _parse_iso_utc(published_at)
        if start <= at <= end:
            out.append((at, tag))
    out.sort(key=lambda x: x[0])
    return out
