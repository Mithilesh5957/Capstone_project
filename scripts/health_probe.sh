#!/usr/bin/env bash
# Continuously ping backend readiness during model loading and log timing metrics.
# Usage: ./scripts/health_probe.sh [BASE_URL] [INTERVAL_S] [OUTFILE]
# Example: ./scripts/health_probe.sh http://localhost:8000 1 startup_metrics.csv
set -u

BASE_URL="${1:-http://localhost:8000}"
INTERVAL="${2:-1}"
OUTFILE="${3:-startup_metrics.csv}"
STABLE_REQUIRED=3     # consecutive 200s to declare deterministic startup proven
MAX_SAMPLES=300

TARGET="$BASE_URL/healthz/readiness"
START_EPOCH=$(date +%s)

if [ ! -f "$OUTFILE" ]; then
  echo "elapsed_s,wall_clock,http_code,latency_ms,phase,model_ready,db_ready,uptime_s" > "$OUTFILE"
fi

echo "Probing $TARGET every ${INTERVAL}s -> $OUTFILE"
stable=0
n=0
while [ "$n" -lt "$MAX_SAMPLES" ]; do
  n=$((n + 1))
  now=$(date +%s)
  elapsed=$((now - START_EPOCH))
  wall=$(date -u +%Y-%m-%dT%H:%M:%SZ)

  body=$(mktemp)
  # -f intentionally NOT used: 503 while loading is an expected sample, not an error
  stats=$(curl -s -o "$body" -w "%{http_code} %{time_total}" --max-time 10 "$TARGET" 2>/dev/null || echo "000 0")
  code=$(echo "$stats" | awk '{print $1}')
  total_s=$(echo "$stats" | awk '{print $2}')
  latency_ms=$(awk "BEGIN {printf \"%d\", $total_s * 1000}")

  # Parse JSON without jq (portable); falls back to raw values on connection failure
  phase=$(grep -o '"phase"[[:space:]]*:[[:space:]]*"[^"]*"' "$body" | sed 's/.*"[[:space:]]*:[[:space:]]*"//;s/"//' | head -n1)
  model=$(grep -o '"model_ready"[[:space:]]*:[[:space:]]*[a-z]*' "$body" | grep -o '[a-z]*$' | head -n1)
  db=$(grep -o '"db_ready"[[:space:]]*:[[:space:]]*[a-z]*' "$body" | grep -o '[a-z]*$' | head -n1)
  uptime=$(grep -o '"uptime_s"[[:space:]]*:[[:space:]]*[0-9.]*' "$body" | grep -o '[0-9.]*$' | head -n1)
  rm -f "$body"
  phase=${phase:-connection_refused}
  model=${model:-false}
  db=${db:-false}
  uptime=${uptime:-0}

  echo "${elapsed},${wall},${code},${latency_ms},${phase},${model},${db},${uptime}" >> "$OUTFILE"
  printf "t=+%ss http=%s latency=%sms phase=%s model=%s db=%s\n" "$elapsed" "$code" "$latency_ms" "$phase" "$model" "$db"

  if [ "$code" = "200" ]; then
    stable=$((stable + 1))
    if [ "$stable" -ge "$STABLE_REQUIRED" ]; then
      echo "READY: backend healthy after ${elapsed}s (${stable} consecutive 200s). Metrics in $OUTFILE"
      exit 0
    fi
  else
    stable=0
  fi
  sleep "$INTERVAL"
done

echo "TIMEOUT: backend never stabilized after $MAX_SAMPLES samples. See $OUTFILE" >&2
exit 1
