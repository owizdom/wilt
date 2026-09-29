"""Timeline and per-event window data for the scroll page.

Requests per minute uses
the same restore guard as measure/metrics.py (a delta is dropped when the
previous counter is 0 and the delta exceeds 5,000).
"""
from collections import Counter

from measure.metrics import PRE_WINDOW, POST_WINDOW, _is_stuck, _rate


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _entry(snapshots, i):
    t, providers = snapshots[i]
    rpm = None
    if i > 0 and providers:
        prev_t, prev_providers = snapshots[i - 1]
        minutes = (t - prev_t).total_seconds() / 60.0
        # No rate for the snapshot right after an empty one: the ids that
        # follow a coordinator restart are new, so nothing is comparable.
        if prev_providers and minutes > 0:
            rpm = _rate([(prev_providers, providers, minutes)])
    return {
        "t": _iso(t),
        "macs": len(providers),
        "stuck": sum(1 for p in providers if _is_stuck(p)) if providers else None,
        "rpm": rpm,
    }


def build_timeline(snapshots):
    """snapshots: time-sorted list of (datetime, providers).

    Returns one {"t", "macs", "stuck", "rpm"} entry per snapshot. rpm is
    null for the first snapshot, for an empty snapshot itself, and for the
    snapshot right after an empty one. stuck is null for an empty snapshot
    (no providers, so no measurement).
    """
    return [_entry(snapshots, i) for i in range(len(snapshots))]


def event_window(snapshots, at, timeline=None):
    """Window entries from at-30 min to at+3 h (clipped to the data) plus
    chips_before, the provider counts by chip_family in the last snapshot
    strictly before `at` (null when no snapshot precedes the event).

    rpm values come from the full snapshot history, so the first entry in
    the window keeps the rate derived from the snapshot just outside it.
    `timeline` may be passed to reuse an already built build_timeline().
    """
    if timeline is None:
        timeline = build_timeline(snapshots)

    start = at - PRE_WINDOW
    end = at + POST_WINDOW
    window = [
        timeline[i] for i, (t, _) in enumerate(snapshots) if start <= t <= end
    ]

    chips_before = None  # no snapshot before the event: not an empty fleet
    for t, providers in reversed(snapshots):
        if t < at:
            counts = Counter(p.get("chip_family") or "other" for p in providers)
            chips_before = dict(counts)
            break

    return {"window": window, "chips_before": chips_before}
