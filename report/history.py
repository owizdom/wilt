"""Permanent event log: merge freshly computed events into history/events.jsonl."""
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone

FINAL_AFTER = timedelta(hours=3, minutes=30)


def _parse(iso):
    return datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _key(e):
    return (e["kind"], e["at"], e["label"])


def merge_history(existing, computed, data_end):
    """Merge computed events into existing history, keyed by (kind, at, label).

    Final events never change. Non-final events take the recomputed values and
    become final once data_end >= at + 3h30m. Events missing from computed are
    kept and marked final. The result is sorted by at ascending.
    """
    stamp = _iso(data_end)
    merged = {}
    for e in existing:
        merged[_key(e)] = dict(e)
    computed_keys = set()
    for c in computed:
        k = _key(c)
        computed_keys.add(k)
        old = merged.get(k)
        if old is not None and old.get("final") is True:
            continue
        e = dict(c)
        e["final"] = data_end >= _parse(c["at"]) + FINAL_AFTER
        e["recorded_at"] = stamp
        merged[k] = e
    for k, e in merged.items():
        if k not in computed_keys and e.get("final") is not True:
            e["final"] = True
    return sorted(merged.values(), key=lambda e: (e["at"], e["kind"], e["label"]))


def load_history(path):
    if not os.path.exists(path):
        return []
    events = []
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                events.append(json.loads(line))
            except ValueError as exc:
                raise ValueError("%s: malformed JSON on line %d: %s" % (path, n, exc))
    return events


def write_history(path, events):
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".events.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for e in events:
                f.write(json.dumps(e, sort_keys=True) + "\n")
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
