"""Per-event metrics.
"""
import statistics
from collections import Counter
from datetime import timedelta

PRE_WINDOW = timedelta(minutes=30)
POST_WINDOW = timedelta(hours=3)
AFTER_RATE_WINDOW = timedelta(minutes=30)
STUCK_AFTER_TARGET = timedelta(minutes=60)
RECOVERY_FRACTION = 0.95
RESTORE_GUARD_DELTA = 5000

STUCK_STATUSES = ("online", "serving")


def _is_stuck(p):
    return p["status"] in STUCK_STATUSES and p["runtime_verified"] is False


def _match_key(p):
    return (
        p["chip"],
        p["memory_gb"],
        p["gpu_cores"],
        p["machine_model"],
        p["requests_served"],
        p["tokens_generated"],
    )


def _consecutive_pairs(snapshots):
    pairs = []
    for i in range(1, len(snapshots)):
        t0, p0 = snapshots[i - 1]
        t1, p1 = snapshots[i]
        minutes = (t1 - t0).total_seconds() / 60.0
        pairs.append((p0, p1, minutes))
    return pairs


def _rate(pairs):
    """pairs: list of (prev_providers, cur_providers, minutes) consecutive
    snapshot pairs. Returns requests-per-minute summed across all matched
    ids and elapsed time. A delta is dropped when the previous counter is 0
    and the delta exceeds 5,000: a lifetime-counter restore after a
    reconnect looks like a large jump from 0, and it is not work. Pairs
    that share no provider ids contribute neither work nor minutes; when no
    pair contributes the result is None (no measurement), never 0.0."""
    total_delta = 0
    total_minutes = 0.0
    for prev_providers, cur_providers, minutes in pairs:
        if minutes <= 0:
            continue
        prev_by_id = dict((p["id"], p) for p in prev_providers)
        pair_delta = 0
        shared = 0
        for cur in cur_providers:
            prev = prev_by_id.get(cur["id"])
            if prev is None:
                continue
            shared += 1
            delta = cur["requests_served"] - prev["requests_served"]
            if prev["requests_served"] == 0 and delta > RESTORE_GUARD_DELTA:
                continue
            pair_delta += delta
        if shared == 0:
            # No provider id in common (an empty snapshot, or a full id
            # turnover): no work was observed, so these minutes do not count.
            continue
        total_delta += pair_delta
        total_minutes += minutes
    if total_minutes <= 0:
        return None
    return total_delta / total_minutes


def measure_event(snapshots, at):
    """snapshots: time-sorted list of (datetime, providers), not necessarily
    limited to the event window. at: the event's UTC datetime.

    Returns the per-event metrics dict from spec section 3, computed from
    snapshots 30 min before to 3 h after `at`, clipped to whatever data is
    available.
    """
    window_start = at - PRE_WINDOW
    window_end = at + POST_WINDOW
    windowed = [s for s in snapshots if window_start <= s[0] <= window_end]

    before = [s for s in windowed if s[0] < at]
    after = [s for s in windowed if s[0] >= at]

    baseline_macs = statistics.median(len(p) for _, p in before) if before else None
    min_macs_after = min((len(p) for _, p in after), default=None)

    drop = None
    if baseline_macs is not None and min_macs_after is not None:
        drop = baseline_macs - min_macs_after

    recovery_minutes = None
    if baseline_macs is not None and baseline_macs > 0:
        threshold = baseline_macs * RECOVERY_FRACTION
        for t, providers in after:
            if len(providers) >= threshold:
                recovery_minutes = (t - at).total_seconds() / 60.0
                break

    requests_per_min_before = _rate(_consecutive_pairs(before))

    after_rate_end = at + AFTER_RATE_WINDOW
    after_for_rate = [s for s in windowed if at <= s[0] <= after_rate_end]
    requests_per_min_after = _rate(_consecutive_pairs(after_for_rate))

    # A missing or empty snapshot observes nothing: its stuck count is None,
    # never 0.
    last_before_providers = before[-1][1] if before else None
    if not last_before_providers:
        last_before_providers = None

    after_target = at + STUCK_AFTER_TARGET
    closest_after_providers = None
    if after:
        closest_after_providers = min(
            after, key=lambda s: abs((s[0] - after_target).total_seconds())
        )[1]
        if not closest_after_providers:
            closest_after_providers = None

    stuck_before = None
    stuck_after = None
    stuck_carried = None
    stuck_by_chip = None
    if last_before_providers is not None:
        stuck_before_list = [p for p in last_before_providers if _is_stuck(p)]
        stuck_before = len(stuck_before_list)
    if closest_after_providers is not None:
        stuck_after_list = [p for p in closest_after_providers if _is_stuck(p)]
        stuck_after = len(stuck_after_list)
    if stuck_before is not None and stuck_after is not None:
        before_counter = Counter(
            _match_key(p) for p in stuck_before_list if p["requests_served"] != 0
        )
        after_counter = Counter(
            _match_key(p) for p in stuck_after_list if p["requests_served"] != 0
        )
        stuck_carried = sum(
            min(before_counter[k], after_counter[k]) for k in after_counter
        )
        stuck_by_chip = dict(
            Counter(p.get("chip_family") or "other" for p in stuck_after_list)
        )

    return {
        "baseline_macs": baseline_macs,
        "min_macs_after": min_macs_after,
        "drop": drop,
        "recovery_minutes": recovery_minutes,
        "requests_per_min_before": requests_per_min_before,
        "requests_per_min_after": requests_per_min_after,
        "stuck_before": stuck_before,
        "stuck_after": stuck_after,
        "stuck_carried": stuck_carried,
        "stuck_by_chip": stuck_by_chip,
    }
