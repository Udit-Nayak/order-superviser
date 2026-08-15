#!/usr/bin/env bash
set -euo pipefail
BASE_URL="http://localhost:8000"

RUN_JSON=$(curl -s -X POST "$BASE_URL/api/runs" \
  -H 'Content-Type: application/json' \
  -d '{"order_id":"ORDER-DEMO-001","default_wake_seconds":30}')
echo "$RUN_JSON"
RUN_ID=$(python -c 'import json,sys; print(json.load(sys.stdin)["run_id"])' <<< "$RUN_JSON")
echo "RUN_ID=$RUN_ID"

curl -s "$BASE_URL/api/runs/$RUN_ID" | python -m json.tool
curl -s -X POST "$BASE_URL/api/runs/$RUN_ID/events" \
  -H 'Content-Type: application/json' \
  -d '{"type":"shipment_delayed","payload":{"delay_hours":4}}' | python -m json.tool
sleep 2
curl -s "$BASE_URL/api/runs/$RUN_ID" | python -m json.tool
