"""Build events.json and EVENTS.md from recorded snapshots and releases.
"""
import json
from datetime import datetime, timezone
import os
from collections import Counter

from detect.events import find_releases, find_restarts
from detect.snapshots import load_stats
from measure.metrics import measure_event
from report.history import load_history, merge_history, write_history
from report.page import render_page
from report.timeline import build_timeline, event_window

STUCK_STATUSES = ("online", "serving")


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(iso):
    return datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _is_stuck(p):
    return p["status"] in STUCK_STATUSES and p["runtime_verified"] is False


def _stuck_now(snapshots):
    if not snapshots:
        return {"at": None, "count": None, "by_chip": {}}
    at, providers = snapshots[-1]
    if not providers:
        # An empty snapshot observes nothing: no count, never a zero.
        return {"at": _iso(at), "count": None, "by_chip": {}}
    stuck = [p for p in providers if _is_stuck(p)]
    by_chip = Counter(p.get("chip_family") or "other" for p in stuck)
    return {"at": _iso(at), "count": len(stuck), "by_chip": dict(by_chip)}


def _fmt_num(x):
    if x is None:
        return "-"
    if isinstance(x, float):
        if x == int(x):
            return str(int(x))
        return "%.1f" % x
    return str(x)


def _fmt_chip(by_chip):
    if not by_chip:
        return "-"
    return ", ".join("%s:%d" % (k, v) for k, v in sorted(by_chip.items()))


def _render_markdown(events, stuck_now, skipped_files):
    lines = []
    lines.append("# Deploy and release events")
    lines.append("")
    lines.append(
        "| Kind | At | Label | Baseline | MinAfter | Drop | RecoveryMin | "
        "ReqPerMinBefore | ReqPerMinAfter | StuckBefore | StuckAfter | "
        "StuckCarried | StuckByChip |"
    )
    lines.append(
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|"
    )
    for e in events:
        lines.append(
            "| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |"
            % (
                e["kind"],
                e["at"],
                e["label"],
                _fmt_num(e["baseline_macs"]),
                _fmt_num(e["min_macs_after"]),
                _fmt_num(e["drop"]),
                _fmt_num(e["recovery_minutes"]),
                _fmt_num(e["requests_per_min_before"]),
                _fmt_num(e["requests_per_min_after"]),
                _fmt_num(e["stuck_before"]),
                _fmt_num(e["stuck_after"]),
                _fmt_num(e["stuck_carried"]),
                _fmt_chip(e["stuck_by_chip"]),
            )
        )
    lines.append("")
    if stuck_now["count"] is None:
        lines.append(
            "Stuck now (as of %s): no measurement, the last snapshot has no "
            "providers." % (stuck_now["at"],)
            if stuck_now["at"] else
            "Stuck now: no measurement, no readable snapshots."
        )
    else:
        lines.append(
            "Stuck now (as of %s): %d providers online/serving with "
            "runtime_verified=false. By chip: %s."
            % (stuck_now["at"], stuck_now["count"], _fmt_chip(stuck_now["by_chip"]))
        )
    lines.append("")
    lines.append("Unreadable snapshot files skipped: %d." % skipped_files)
    lines.append("")
    return "\n".join(lines)


def build_report(raw_dir, releases_path, out_dir, history_path=None):
    """Read raw_dir (stats/*.json.gz) and releases_path, write
    out_dir/events.json, out_dir/EVENTS.md and out_dir/index.html.

    Returns {"events": [...], "skipped_files": int, "stuck_now": {...}}.
    """
    snapshots, skipped = load_stats(raw_dir)

    events_raw = []  # (at_datetime, kind, label, metrics_dict)

    for t in find_restarts(snapshots):
        events_raw.append((t, "restart", "coordinator restart", measure_event(snapshots, t)))

    if snapshots:
        start, end = snapshots[0][0], snapshots[-1][0]
        with open(releases_path) as f:
            releases = json.load(f)
        for t, tag in find_releases(releases, start, end):
            events_raw.append((t, "release", tag, measure_event(snapshots, t)))

    events_raw.sort(key=lambda e: e[0], reverse=True)

    events = []
    for at, kind, label, metrics in events_raw:
        event = {"kind": kind, "at": _iso(at), "label": label}
        event.update(metrics)
        events.append(event)

    all_events = None
    if history_path:
        computed_keys = set((e["kind"], e["at"], e["label"]) for e in events)
        existing = load_history(history_path)
        if snapshots:
            merged = merge_history(existing, events, snapshots[-1][0])
            write_history(history_path, merged)
        else:
            merged = existing
        all_events = sorted(merged, key=lambda e: e["at"], reverse=True)
        by_key = dict(((e["kind"], e["at"], e["label"]), e) for e in all_events)
        events = all_events
        events_raw = [
            (_parse(e["at"]), e["kind"], e["label"], None)
            for e in all_events
            if (e["kind"], e["at"], e["label"]) in computed_keys
        ]
        events_raw_events = [by_key[(k, _iso(a), l)] for a, k, l, _m in events_raw]
    else:
        events_raw_events = events

    stuck_now = _stuck_now(snapshots)

    os.makedirs(out_dir, exist_ok=True)

    with open(os.path.join(out_dir, "events.json"), "w") as f:
        json.dump(events, f, indent=2)

    with open(os.path.join(out_dir, "EVENTS.md"), "w") as f:
        f.write(_render_markdown(events, stuck_now, skipped))

    # The page data is the same events plus a per-event window and the chip
    # mix before it; events.json and EVENTS.md stay unchanged.
    timeline = build_timeline(snapshots)
    page_events = []
    for (at, _kind, _label, _metrics), event in zip(events_raw, events_raw_events):
        page_event = dict(event)
        page_event.update(event_window(snapshots, at, timeline=timeline))
        page_events.append(page_event)

    span = {
        "start": _iso(snapshots[0][0]) if snapshots else None,
        "end": _iso(snapshots[-1][0]) if snapshots else None,
        "snapshots": len(snapshots),
    }
    page_data = {
        "timeline": timeline,
        "events": page_events,
        "stuck_now": stuck_now,
        "span": span,
    }
    if all_events is not None:
        page_data["all_events"] = all_events
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(render_page(page_data))

    return {"events": events, "skipped_files": skipped, "stuck_now": stuck_now}
