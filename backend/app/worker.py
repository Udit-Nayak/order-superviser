import asyncio

from temporalio.client import Client
from temporalio.worker import Worker

from app.activities.agent_activities import (
    classify_event_activity,
    run_agent_activity,
    run_final_summary_activity,
)
from app.activities.order_state_activities import get_order_state_activity
from app.activities.persistence_activities import (
    persist_final_summary_activity,
    persist_instruction_activity,
    persist_memory_activity,
    persist_run_status_activity,
    persist_timeline_activity,
)
from app.activities.tool_activities import execute_tool_activity
from app.config import settings
from app.workflows.order_supervisor_workflow import OrderSupervisorWorkflow


async def main() -> None:
    client = await Client.connect(
        settings.temporal_host,
        namespace=settings.temporal_namespace,
    )

    print(
        f"Temporal hybrid-monitoring worker connected to {settings.temporal_host} "
        f"namespace={settings.temporal_namespace} "
        f"task_queue={settings.temporal_task_queue}",
        flush=True,
    )

    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=[OrderSupervisorWorkflow],
        activities=[
            classify_event_activity,
            run_agent_activity,
            run_final_summary_activity,
            get_order_state_activity,
            execute_tool_activity,
            persist_timeline_activity,
            persist_memory_activity,
            persist_run_status_activity,
            persist_instruction_activity,
            persist_final_summary_activity,
        ],
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
