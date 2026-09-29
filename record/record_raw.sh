#!/usr/bin/env bash
# Raw recorder. Saves public Darkbloom API responses
# to data/raw/<endpoint>/<utc>.json.gz and nothing else. No parsing here, so a
# bug in analysis code can never lose data. Public endpoints only, one /v1/stats
# fetch per 90 s (the console itself refreshes every 30 s while visible).
set -u
cd "$(dirname "$0")/.."
API=https://api.darkbloom.dev
INTERVAL=${INTERVAL:-90}
mkdir -p data/raw/stats data/raw/capacity data/raw/pricing data/raw/series24h data/raw/series30m
log() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$*" >> data/recorder.log; }

fetch() { # endpoint dir
  local ts out
  ts=$(date -u +%Y%m%dT%H%M%SZ)
  out="data/raw/$2/$ts.json.gz"
  if curl -sf -m 45 "$API$1" | gzip -c > "$out.tmp" && [ "$(gzip -dc "$out.tmp" | head -c 1)" = "{" ]; then
    mv "$out.tmp" "$out"
  else
    rm -f "$out.tmp"; log "FAIL $1"
  fi
}

log "start pid $$ interval ${INTERVAL}s"
i=0
while true; do
  fetch /v1/stats stats
  fetch /v1/models/capacity capacity
  fetch "/v1/network/series?window=30m" series30m
  if [ $((i % 20)) -eq 0 ]; then          # every 30 min
    fetch /v1/pricing pricing
    fetch "/v1/network/series?window=24h" series24h
  fi
  i=$((i + 1))
  sleep "$INTERVAL"
done
