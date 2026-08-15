#!/usr/bin/env python
"""Run a saved Order Supervisor scenario against a running FastAPI backend.

Usage:
    python scripts/run_scenario.py scenarios/delayed_shipment.json

No third-party HTTP library is required; this script uses Python's stdlib.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


TERMINAL_STATUSES = {"completed", "terminated", "failed"}


def request_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    timeout: float = 300.0,
) -> Any:
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from {url}: {raw}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach {url}: {exc.reason}") from exc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario", help="Path to a scenario JSON file")
    parser.add_argument(
        "--api",
        default="http://localhost:8000",
        help="FastAPI base URL (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--poll-timeout",
        type=float,
        default=180.0,
        help="Seconds to wait for the run to become terminal after scenario playback",
    )
    args = parser.parse_args()

    path = Path(args.scenario)
    if not path.exists():
        print(f"Scenario file not found: {path}", file=sys.stderr)
        return 2

    scenario = json.loads(path.read_text(encoding="utf-8"))
    api = args.api.rstrip("/")

    print(f"Scenario: {path}")
    print(f"Order:    {scenario.get('order_id')}")
    print(f"Backend:  {api}")
    print("\nStarting self-contained scenario run...")

    started = request_json(
        "POST",
        f"{api}/api/scenarios/run",
        scenario,
        timeout=600.0,
    )

    run_id = started["run_id"]
    print(f"RUN_ID={run_id}")
    print(f"Workflow={started['workflow_id']}")
    print(f"Scenario steps dispatched: {len(started.get('scenario_trace', []))}")

    deadline = time.time() + args.poll_timeout
    last_status = None

    while time.time() < deadline:
        state = request_json("GET", f"{api}/api/runs/{run_id}")
        status = state.get("status")
        if status != last_status:
            print(f"status -> {status}")
            last_status = status
        if status in TERMINAL_STATUSES:
            print("\nScenario finished.")
            print(json.dumps(state, indent=2))
            return 0
        time.sleep(2)

    print(
        f"\nScenario playback finished, but run did not reach a terminal state "
        f"within {args.poll_timeout:.0f}s. The workflow is still durable and can "
        f"continue in Temporal.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
