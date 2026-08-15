from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Allow: python scripts/reset_all_demo_data.py
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import delete, select
from temporalio.client import Client

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import (
    FinalSummary,
    Instruction,
    MemorySnapshot,
    Run,
    Supervisor,
    TimelineEntry,
    WorkflowTemplate,
)

# Hybrid-monitoring table/model may be called OrderRuntimeState in your current overlay.
try:
    from app.models import OrderRuntimeState
except ImportError:
    OrderRuntimeState = None


async def terminate_temporal_workflows() -> int:
    """Terminate every workflow referenced by the current runs table."""
    async with AsyncSessionLocal() as session:
        workflow_ids = list(
            (
                await session.execute(
                    select(Run.workflow_id)
                    .where(Run.workflow_id.is_not(None))
                )
            ).scalars().all()
        )

    if not workflow_ids:
        print("No workflow IDs found in Postgres.")
        return 0

    try:
        client = await Client.connect(
            settings.temporal_host,
            namespace=settings.temporal_namespace,
        )
    except Exception as exc:
        print(f"Could not connect to Temporal; skipping termination: {exc}")
        return 0

    terminated = 0

    for workflow_id in workflow_ids:
        try:
            handle = client.get_workflow_handle(workflow_id)
            await handle.terminate(reason="Demo reset")
            terminated += 1
            print(f"Terminated Temporal workflow: {workflow_id}")
        except Exception as exc:
            # Closed/not-found workflows are harmless during reset.
            print(f"Skipped Temporal workflow {workflow_id}: {exc}")

    return terminated


async def clear_postgres(delete_supervisors: bool) -> dict[str, int]:
    """Delete demo/runtime rows in FK-safe order."""
    counts: dict[str, int] = {}

    async with AsyncSessionLocal() as session:
        # Children of runs first.
        delete_order = [
            ("final_summaries", FinalSummary),
            ("instructions", Instruction),
            ("memory_snapshots", MemorySnapshot),
            ("timeline_entries", TimelineEntry),
        ]

        if OrderRuntimeState is not None:
            delete_order.append(("order_runtime_states", OrderRuntimeState))

        delete_order.append(("runs", Run))

        if delete_supervisors:
            delete_order.extend(
                [
                    ("workflow_templates", WorkflowTemplate),
                    ("supervisors", Supervisor),
                ]
            )

        for name, model in delete_order:
            result = await session.execute(delete(model))
            counts[name] = int(result.rowcount or 0)

        await session.commit()

    return counts


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Terminate Order Supervisor Temporal workflows and clear demo data."
    )
    parser.add_argument(
        "--keep-supervisors",
        action="store_true",
        help="Keep supervisors and workflow templates; only clear runs/runtime data.",
    )
    args = parser.parse_args()

    print("=== Order Supervisor full demo reset ===")

    terminated = await terminate_temporal_workflows()
    print(f"\nTemporal workflows terminated: {terminated}")

    counts = await clear_postgres(
        delete_supervisors=not args.keep_supervisors
    )

    print("\nDeleted from Postgres/Supabase:")
    for table, count in counts.items():
        print(f"  {table}: {count}")

    print("\nReset complete.")
    print("The Kanban should now be empty after frontend refresh.")
    print(
        "IMPORTANT: terminated Temporal workflow histories still remain visible "
        "in Temporal UI. For a completely empty Temporal UI, stop Temporal and "
        "restart it with a NEW --db-filename."
    )


if __name__ == "__main__":
    asyncio.run(main())
