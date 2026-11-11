#!/usr/bin/env bash
# Start, stop and inspect the two local development servers.
#
# Ports rather than bare pids are the source of truth: a stale pid file after a crash must
# not leave a server running that `make stop` cannot see.
set -euo pipefail

API_PORT="${FIREBRIEF_API_PORT:-8010}"
WEB_PORT="${FIREBRIEF_WEB_PORT:-5173}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN="$ROOT/.run"
API_LOG="$RUN/api.log"
WEB_LOG="$RUN/web.log"
API_PID="$RUN/api.pid"
WEB_PID="$RUN/web.pid"

mkdir -p "$RUN"

listening() { lsof -tiTCP:"$1" -sTCP:LISTEN 2>/dev/null || true; }

wait_for_port() {
  local port="$1" tries=0
  until [ -n "$(listening "$port")" ] || [ "$tries" -ge 40 ]; do
    sleep 0.25
    tries=$((tries + 1))
  done
}

start_one() {
  local name="$1" port="$2" log="$3" pidfile="$4"
  shift 4
  if [ -n "$(listening "$port")" ]; then
    echo "$name already running on :$port (pid $(listening "$port" | head -1))"
    return 0
  fi
  : >"$log"
  ( "$@" >"$log" 2>&1 & echo $! >"$pidfile" )
  wait_for_port "$port"
  if [ -z "$(listening "$port")" ]; then
    echo "$name failed to start; last lines of $log:" >&2
    tail -n 20 "$log" >&2 || true
    return 1
  fi
  echo "$name started on :$port (pid $(listening "$port" | head -1)), log $log"
}

stop_one() {
  local name="$1" port="$2" pidfile="$3"
  local pids
  pids="$(listening "$port")"
  if [ -z "$pids" ] && [ -f "$pidfile" ]; then
    pids="$(cat "$pidfile" 2>/dev/null || true)"
  fi
  if [ -z "$pids" ]; then
    echo "$name is not running"
    rm -f "$pidfile"
    return 0
  fi
  # SIGTERM first, so uvicorn and Vite shut down their children cleanly.
  kill $pids 2>/dev/null || true
  local tries=0
  while [ -n "$(listening "$port")" ] && [ "$tries" -lt 20 ]; do
    sleep 0.25
    tries=$((tries + 1))
  done
  pids="$(listening "$port")"
  if [ -n "$pids" ]; then
    kill -9 $pids 2>/dev/null || true
    echo "$name did not stop on SIGTERM; killed"
  else
    echo "$name stopped"
  fi
  rm -f "$pidfile"
}

status_one() {
  local name="$1" port="$2"
  local pids
  pids="$(listening "$port")"
  if [ -n "$pids" ]; then
    echo "$name running on :$port (pid $(echo "$pids" | tr '\n' ' '))"
  else
    echo "$name stopped (:$port)"
  fi
}

case "${1:-}" in
  start)
    cd "$ROOT"
    start_one "api" "$API_PORT" "$API_LOG" "$API_PID" \
      uv run uvicorn firebrief.api.dev:app --reload --port "$API_PORT" --host 127.0.0.1
    start_one "web" "$WEB_PORT" "$WEB_LOG" "$WEB_PID" \
      npm --prefix web run dev -- --host 127.0.0.1 --port "$WEB_PORT"
    echo
    echo "web: http://127.0.0.1:$WEB_PORT/sign-in?tenant=018f0000-0000-7000-8000-0000000000aa"
    echo "api: http://127.0.0.1:$API_PORT/health"
    echo "logs: make logs"
    ;;
  stop)
    stop_one "web" "$WEB_PORT" "$WEB_PID"
    stop_one "api" "$API_PORT" "$API_PID"
    ;;
  restart)
    "$0" stop
    "$0" start
    ;;
  status)
    status_one "api" "$API_PORT"
    status_one "web" "$WEB_PORT"
    ;;
  logs)
    touch "$API_LOG" "$WEB_LOG"
    tail -n 40 -f "$API_LOG" "$WEB_LOG"
    ;;
  *)
    echo "usage: $0 {start|stop|restart|status|logs}" >&2
    exit 2
    ;;
esac
