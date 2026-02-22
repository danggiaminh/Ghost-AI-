#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8080}"
COOKIE_FILE="/tmp/ghost_smoke_cookie.txt"
EMAIL="smoke$(date +%s)@example.com"
PASSWORD="StrongPass123"

rm -f "$COOKIE_FILE"

echo "[1] health"
curl -fsS "$BASE_URL/health" >/dev/null

echo "[2] register"
curl -fsS -c "$COOKIE_FILE" -b "$COOKIE_FILE" -X POST "$BASE_URL/auth/register" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" >/dev/null

echo "[3] refresh rotation"
curl -fsS -c "$COOKIE_FILE" -b "$COOKIE_FILE" -X POST "$BASE_URL/auth/refresh" \
  -H 'Content-Type: application/json' -d '{}' >/dev/null

echo "[4] stream"
STREAM_OUT="$(curl -fsS -N -c "$COOKIE_FILE" -b "$COOKIE_FILE" -X POST "$BASE_URL/chat/stream" \
  -H 'Content-Type: application/json' \
  -d '{"message":"debug smoke check"}')"
if [[ "$STREAM_OUT" != *"event: meta"* ]]; then
  echo "Stream validation failed"
  exit 1
fi

echo "Smoke test passed"
