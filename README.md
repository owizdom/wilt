# wilt

Status: discontinued on 2026-10-01. The hosted page is offline and the recording and publishing workflows are disabled. The code still runs locally on recorded snapshots. One known issue was left unfixed: GitHub ran the 10-minute schedule only every few hours, and with that much provider id churn between snapshots the restart detector flagged false restarts, so `history/events.jsonl` contains false restart events from 2026-09-30 onward.

Every Darkbloom coordinator restart and provider release, and the Macs it leaves wilted.

wilt scores Darkbloom coordinator deploys and provider releases from outside the system. It reads recorded public snapshots and nothing else.

Darkbloom ships several times a week. Nobody outside the project measures what each ship does to the fleet of Mac providers. wilt reads a folder of recorded `/v1/stats` snapshots plus a list of provider releases. It finds the restart and release events and scores each one: how many Macs dropped, how fast the fleet came back, how much request throughput was lost, and how many providers were stuck.

A provider is stuck when its status is online or serving and `runtime_verified` is false. It looks healthy in the public listing and cannot serve.

## Quick start

The repo ships a real recording of one coordinator restart. This command runs on it directly:

```
python3 wilt.py --raw tests/fixtures/restart_20260928 --releases tests/fixtures/releases.json --out out/
```

It writes three files into `out/`:

- `index.html`, a scroll page that tells the story of the run. It is one self-contained file with no network requests, so it opens in any browser with a double-click.
- `events.json`, the full scored event list.
- `EVENTS.md`, one table row per event, newest first, plus a stuck-now line from the last snapshot.

The command also prints a one-line summary.

## Inputs

- A raw data directory with `stats/<UTC timestamp>.json.gz` snapshot files, for example `./data/raw`. The snapshot time comes from the file name, never from the recorded body. `record/record_raw.sh` writes this layout.
- A releases JSON file: a list of objects with `tag` or `tag_name`, and `published_at`. Entries with a null `published_at` are skipped.

Produce the releases file from GitHub with the `gh` CLI:

```
gh api repos/Layr-Labs/d-inference/releases --paginate > releases.json
```

The output works as it is, because the tool accepts the `tag_name` key that GitHub returns. Pass it with `--releases releases.json`.

Files that fail to read are skipped and counted. That covers a bad gzip container, a gzip file cut short at the byte level, corrupted compressed bytes, and a valid gzip file around truncated JSON.

A run against your own recording looks like this:

```
python3 wilt.py --raw ./data/raw --releases ./releases.json --out ./out
```

## How events are detected

A restart fires on a snapshot with zero providers. That includes the first snapshot in the recording. It also fires on a snapshot where fewer than 50% of its provider ids were present in the previous readable snapshot.

Consecutive qualifying snapshots within 10 minutes count as one event. A release event fires once per release whose `published_at` falls inside the recorded span.

## What gets measured per event

The window runs from 30 minutes before the event to 3 hours after, clipped to the available data.

- `baseline_macs`: the median provider count before the event.
- `min_macs_after` and `drop`: the lowest post-event count and how far it fell from baseline.
- `recovery_minutes`: the time to the first snapshot back at 95% of baseline, or null if the fleet never got there inside the window.
- `requests_per_min_before` and `requests_per_min_after` (first 30 minutes): built from `requests_served` deltas between consecutive snapshots, for provider ids present in both. A delta is dropped when the previous counter was 0 and the delta exceeds 5,000. A lifetime counter restored after a reconnect looks like a large jump from 0, and it is not work. A pair of snapshots that shares no provider ids, such as one with an empty snapshot, contributes neither work nor minutes. When no pair contributes the value is null, shown as "-" in EVENTS.md and "no measurement" on the page.
- `stuck_before` and `stuck_after`: stuck providers in the last snapshot before the event and in the snapshot closest to 60 minutes after. Each is null when that snapshot is missing or has 0 providers.
- `stuck_carried`: stuck-after providers matched to a stuck-before provider on chip, `memory_gb`, `gpu_cores`, `machine_model`, `requests_served` and `tokens_generated`. The match counts only when `requests_served` is non-zero. The non-zero test is on `requests_served`, not on tokens. A zero-counter match is coincidence, not the same Mac.
- `stuck_by_chip`: stuck-after providers grouped by chip family.

## Real result

The fixture in `tests/fixtures/restart_20260928` holds public snapshots recorded on 2026-09-28 from 20:10Z to 21:48Z. The run finds one restart event and no release events. No release in `tests/fixtures/releases.json` falls inside that span.

The EVENTS.md row:

| Kind | At | Label | Baseline | MinAfter | Drop | RecoveryMin | ReqPerMinBefore | ReqPerMinAfter | StuckBefore | StuckAfter | StuckCarried | StuckByChip |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| restart | 2026-09-28T20:42:37Z | coordinator restart | 1179.5 | 0 | 1179.5 | 1.6 | 4292.6 | 4445.3 | 12 | 12 | 6 | M1:6, M2:1, M4:4, M5:1 |

The fleet dropped from about 1,180 Macs (median of the 30 minutes before) to 0 in one snapshot. It was back above 95% of baseline 1.55 minutes later. `events.json` keeps 1.55, and EVENTS.md rounds it to 1.6.

12 providers were stuck before the restart and 12 after. 6 of them matched the same hardware with identical non-zero request counters, so they stayed stuck through the restart. The rest cannot be matched from public counters.

## The scroll page

`out/index.html` is built from the same data. It opens on the stuck-now count, then walks through the fleet by chip family, the restart as a scrubbed clock, request throughput, the stuck Macs left behind, the stuck count across the whole recording, and a table of every event.

When the last snapshot has no providers, or the recording has no readable snapshot, the stuck-now count is a "-" with an explanation and never a 0. The same holds for the stuck counts around an event. `stuck_before` is null when no snapshot with providers falls in the 30 minutes before the event, and `stuck_after` is null when none falls in the 3 hours after it. `stuck_carried` and `stuck_by_chip` are null when either side is null, while the other side keeps its observed value. `EVENTS.md` and the table show "-" for null, and section 5 of the page states which side has no stuck count.

The page needs no server. It respects `prefers-reduced-motion` and works at phone width.

## Hosted recording

A GitHub Actions workflow polls the public stats endpoint about every 10 minutes and keeps the last 14 days of snapshots on a single-commit `data` branch. GitHub may run schedules late, so gaps of several minutes are normal.

Recovery times measured from this recording are coarser than from a 95-second recorder, because a restart can only be timed to the nearest snapshot. At a 10-minute cadence a short outage can fall between two snapshots, so drops and minimum-Mac counts can be understated as well.

A second workflow rebuilds `site/index.html` from the `data` branch hourly and pushes to `main` only when the page changed. When the Vercel project is connected to the repo, each push to `main` deploys through its Git integration, and the `data` branch is skipped. The workflows use no secrets beyond the built-in `GITHUB_TOKEN`.

## Permanent event log

The data branch keeps 14 days of snapshots, so `history/events.jsonl` on `main` keeps every scored event for good, one JSON line each. An event is rewritten on each run until 3.5 hours after it happened, then it is final and never changes; the hourly workflow commits the file with the page, and the table on the page lists the whole log.

## What it does not do

wilt does not alert or notify. It does not analyze routing, earnings or per-model behavior. It never writes to any Darkbloom endpoint.

The local recorder in `record/record_raw.sh` polls the public Darkbloom API with plain GET requests on a fixed interval. It stores each full raw response and parses nothing, so a bug in the analysis code cannot lose recorded data. The hosted `record/snapshot.py` keeps only the 12 fields the analysis reads.

## Tests

```
python3 -m unittest discover -s tests -t .
```

The code uses only the standard library and runs on Python 3.9 and later. The workflow checks in the test suite need either PyYAML or `actionlint` installed, and fail without one of them.
