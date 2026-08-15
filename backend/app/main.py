import asyncio
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio.client import Client
from temporalio.service import RPCError

from app.config import settings
from app.database import get_db
from app.models import (
    FinalSummary,
    Instruction,
    MemorySnapshot,
    OrderRuntimeState,
    Run,
    Supervisor,
    TimelineEntry,
    WorkflowTemplate,
)
from app.schemas import (
    CreateSupervisorRequest,
    ExternalOrderStatePatch,
    HumanActionRequest,
    IncomingOrderRequest,
    InstructionRequest,
    OrderEventRequest,
    SaveWorkflowTemplateRequest,
    StartRunRequest,
)
from app.workflow_defaults import default_workflow_blocks
from app.workflows.order_supervisor_workflow import OrderSupervisorWorkflow


TERMINAL_STATUSES = {"completed", "terminated", "failed"}
ACTIVE_STATUSES = {
    "active",
    "sleeping",
    "thinking",
    "waiting_review",
    "post_delivery",
}


def workflow_id_for(run_id: str) -> str:
    return f"order-supervisor-{run_id}"


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.temporal = await Client.connect(
        settings.temporal_host,
        namespace=settings.temporal_namespace,
    )
    yield


app = FastAPI(
    title="Order Supervisor - Hybrid Event + Polling",
    version="1.1.0",
    description="Temporal order supervisor using immediate event signals plus scheduled external-state polling.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def temporal_client(request: Request) -> Client:
    return request.app.state.temporal


def get_handle(request: Request, run_id: str):
    return temporal_client(request).get_workflow_handle(
        workflow_id_for(run_id)
    )


def temporal_http_error(exc: Exception) -> HTTPException:
    message = str(exc)
    lower = message.lower()
    if "not found" in lower:
        return HTTPException(status_code=404, detail="Run/workflow not found")
    if "completed" in lower or "closed" in lower or "not running" in lower:
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Run is already terminal and cannot accept this signal",
        )
    return HTTPException(status_code=502, detail=f"Temporal error: {message}")


def supervisor_to_dict(row: Supervisor) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "name": row.name,
        "base_instruction": row.base_instruction,
        "tools_enabled": row.tools_enabled,
        "model_config": row.model_config,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def template_to_dict(row: WorkflowTemplate) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "supervisor_id": str(row.supervisor_id),
        "name": row.name,
        "blocks": row.blocks,
        "active": row.active,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def run_row_to_dict(row: Run) -> dict[str, Any]:
    return {
        "run_id": str(row.id),
        "supervisor_id": str(row.supervisor_id),
        "order_id": row.order_id,
        "workflow_id": row.workflow_id,
        "status": row.status,
        "next_wake_at": row.next_wake_at.isoformat()
        if row.next_wake_at
        else None,
        "created_at": row.created_at.isoformat()
        if row.created_at
        else None,
        "updated_at": row.updated_at.isoformat()
        if row.updated_at
        else None,
        "completed_at": row.completed_at.isoformat()
        if row.completed_at
        else None,
    }


def external_state_to_dict(row: OrderRuntimeState) -> dict[str, Any]:
    return {
        "run_id": str(row.run_id),
        "order_id": row.order_id,
        "payment_status": row.payment_status,
        "shipment_status": row.shipment_status,
        "delivery_status": row.delivery_status,
        "total_delay_hours": float(row.total_delay_hours or 0.0),
        "latest_eta": row.latest_eta.isoformat() if row.latest_eta else None,
        "refund_status": row.refund_status,
        "refund_version": row.refund_version,
        "customer_message": row.customer_message,
        "customer_message_version": row.customer_message_version,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _event_type_for_patch(changes: dict[str, Any]) -> str:
    if changes.get("delivery_status") == "delivered" or changes.get("shipment_status") == "delivered":
        return "delivered"
    if changes.get("refund_status") == "requested":
        return "refund_requested"
    if changes.get("customer_message") is not None:
        return "customer_message_received"
    if changes.get("additional_delay_hours") is not None or changes.get("shipment_status") == "delayed":
        return "shipment_delayed"
    if changes.get("shipment_status") in {"created", "in_transit"}:
        return "shipment_created"
    if changes.get("payment_status") == "confirmed":
        return "payment_confirmed"
    if changes.get("payment_status") == "failed":
        return "payment_failed"
    return "order_state_changed"


def _apply_event_to_runtime_state(
    state: OrderRuntimeState,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    """Keep legacy /events and CLI scenarios compatible with the hybrid source of truth."""
    if event_type == "payment_confirmed":
        state.payment_status = "confirmed"
    elif event_type == "payment_failed":
        state.payment_status = "failed"
    elif event_type == "shipment_created":
        state.shipment_status = "created"
    elif event_type == "shipment_delayed":
        state.shipment_status = "delayed"
        delay = payload.get("delay_hours", payload.get("additional_delay_hours", 0))
        try:
            state.total_delay_hours = float(state.total_delay_hours or 0.0) + float(delay or 0.0)
        except (TypeError, ValueError):
            pass
        eta = payload.get("new_eta") or payload.get("latest_eta")
        if eta:
            from datetime import datetime
            try:
                state.latest_eta = datetime.fromisoformat(str(eta).replace("Z", "+00:00"))
            except ValueError:
                pass
    elif event_type == "delivered":
        state.shipment_status = "delivered"
        state.delivery_status = "delivered"
    elif event_type == "refund_requested":
        state.refund_status = "requested"
        state.refund_version = int(state.refund_version or 0) + 1
    elif event_type == "customer_message_received":
        state.customer_message = str(payload.get("message", ""))
        state.customer_message_version = int(state.customer_message_version or 0) + 1


async def load_run_or_404(db: AsyncSession, run_id: str) -> Run:
    try:
        parsed = UUID(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc

    row = await db.get(Run, parsed)
    if not row:
        raise HTTPException(status_code=404, detail="Run not found")
    return row


async def ensure_signalable(db: AsyncSession, run_id: str) -> Run:
    row = await load_run_or_404(db, run_id)
    if row.status in TERMINAL_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Run is already {row.status} and cannot accept new signals",
        )
    return row


async def active_template(
    db: AsyncSession,
    supervisor_id: UUID,
) -> WorkflowTemplate | None:
    return (
        await db.execute(
            select(WorkflowTemplate)
            .where(
                WorkflowTemplate.supervisor_id == supervisor_id,
                WorkflowTemplate.active.is_(True),
            )
            .order_by(WorkflowTemplate.updated_at.desc())
        )
    ).scalars().first()


async def ensure_active_template(
    db: AsyncSession,
    supervisor_id: UUID,
) -> WorkflowTemplate:
    row = await active_template(db, supervisor_id)
    if row:
        return row

    row = WorkflowTemplate(
        supervisor_id=supervisor_id,
        name="Default order lifecycle",
        blocks=default_workflow_blocks(),
        active=True,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


def derive_block_state(
    timeline_rows: list[TimelineEntry],
) -> tuple[dict | None, list[dict]]:
    current: dict | None = None
    completed: list[dict] = []

    for item in timeline_rows:
        if item.type != "workflow_block":
            continue

        payload = item.payload or {}
        block = {
            "id": payload.get("block_id"),
            "label": payload.get("block_label"),
            "block_type": payload.get("block_type"),
        }

        if payload.get("state") == "entered":
            current = block
        elif payload.get("state") == "completed":
            completed.append(
                {
                    **block,
                    "completed_at": item.created_at.isoformat(),
                    "reason": payload.get("reason"),
                }
            )
            if current and current.get("id") == block.get("id"):
                current = None

    return current, completed


async def persisted_run_state(
    db: AsyncSession,
    row: Run,
) -> dict[str, Any]:
    timeline = (
        await db.execute(
            select(TimelineEntry)
            .where(TimelineEntry.run_id == row.id)
            .order_by(TimelineEntry.created_at.asc())
        )
    ).scalars().all()

    memory = await db.get(MemorySnapshot, row.id)
    instructions = (
        await db.execute(
            select(Instruction)
            .where(
                Instruction.run_id == row.id,
                Instruction.active.is_(True),
            )
            .order_by(Instruction.created_at.asc())
        )
    ).scalars().all()

    final_summary = await db.get(FinalSummary, row.id)
    external_state = await db.get(OrderRuntimeState, row.id)
    current_block, block_history = derive_block_state(timeline)

    result = run_row_to_dict(row)
    result.update(
        {
            "source": "supabase",
            "timeline": [
                {
                    "type": item.type,
                    "summary": item.summary,
                    "payload": item.payload,
                    "created_at": item.created_at.isoformat(),
                }
                for item in timeline
            ],
            "memory_summary": memory.summary if memory else "",
            "key_facts": memory.key_facts if memory else {},
            "instructions": [item.text for item in instructions],
            "current_block": current_block,
            "block_history": block_history,
            "human_intervention_required": (
                row.status == "waiting_review"
            ),
            "external_state": external_state_to_dict(external_state) if external_state else {},
            "final_summary": (
                {
                    "summary": final_summary.summary,
                    "actions_taken": final_summary.actions_taken,
                    "key_learnings": final_summary.key_learnings,
                    "recommendations": final_summary.recommendations,
                    "created_at": final_summary.created_at.isoformat(),
                }
                if final_summary
                else None
            ),
        }
    )
    return result


async def create_run_internal(
    *,
    supervisor: Supervisor,
    order_id: str,
    request: Request,
    db: AsyncSession,
) -> dict[str, Any]:
    existing = (
        await db.execute(
            select(Run).where(
                Run.order_id == order_id,
                Run.status.in_(ACTIVE_STATUSES),
            )
        )
    ).scalars().first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Order {order_id} already has active run {existing.id}."
            ),
        )

    template = await ensure_active_template(db, supervisor.id)

    run_uuid = uuid4()
    run_id = str(run_uuid)
    workflow_id = workflow_id_for(run_id)

    row = Run(
        id=run_uuid,
        supervisor_id=supervisor.id,
        order_id=order_id,
        workflow_id=workflow_id,
        status="active",
    )

    # IMPORTANT:
    # order_runtime_states.run_id is a foreign key to runs.id.
    # Flush the parent Run first so PostgreSQL can validate the child FK.
    db.add(row)
    await db.flush()

    runtime_state = OrderRuntimeState(
        run_id=run_uuid,
        order_id=order_id,
        payment_status="pending",
        shipment_status="not_created",
        delivery_status="pending",
        total_delay_hours=0.0,
        refund_status="none",
    )
    db.add(runtime_state)

    await db.commit()

    supervisor_config = supervisor_to_dict(supervisor)
    supervisor_config.pop("id", None)
    supervisor_config.pop("created_at", None)

    input_data = {
        "run_id": run_id,
        "order_id": order_id,
        "supervisor_id": str(supervisor.id),
        "supervisor_config": supervisor_config,
        "workflow_template": template_to_dict(template),
    }

    try:
        await temporal_client(request).start_workflow(
            OrderSupervisorWorkflow.run,
            input_data,
            id=workflow_id,
            task_queue=settings.temporal_task_queue,
        )
    except Exception as exc:
        row.status = "failed"
        await db.commit()
        if isinstance(exc, RPCError):
            raise temporal_http_error(exc) from exc
        raise HTTPException(
            status_code=502,
            detail=f"Could not start workflow: {exc}",
        ) from exc

    return {
        "run_id": run_id,
        "order_id": order_id,
        "workflow_id": workflow_id,
        "supervisor_id": str(supervisor.id),
        "workflow_template_id": str(template.id),
        "workflow_template_name": template.name,
        "status": "started",
    }


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/supervisors", status_code=status.HTTP_201_CREATED)
async def create_supervisor(
    body: CreateSupervisorRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = Supervisor(
        name=body.name,
        base_instruction=body.base_instruction,
        tools_enabled=body.tools_enabled,
        wake_aggressiveness="high",
        model_config=body.llm_config.model_dump(mode="json"),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    template = WorkflowTemplate(
        supervisor_id=row.id,
        name="Default order lifecycle",
        blocks=default_workflow_blocks(),
        active=True,
    )
    db.add(template)
    await db.commit()

    return supervisor_to_dict(row)


@app.get("/api/supervisors")
async def list_supervisors(
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            select(Supervisor).order_by(Supervisor.created_at.desc())
        )
    ).scalars().all()
    return [supervisor_to_dict(row) for row in rows]


@app.post("/api/workflow-templates", status_code=status.HTTP_201_CREATED)
async def save_workflow_template(
    body: SaveWorkflowTemplateRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    supervisor = await db.get(Supervisor, body.supervisor_id)
    if not supervisor:
        raise HTTPException(status_code=404, detail="Supervisor not found")

    if body.active:
        await db.execute(
            update(WorkflowTemplate)
            .where(WorkflowTemplate.supervisor_id == body.supervisor_id)
            .values(active=False)
        )

    row = WorkflowTemplate(
        supervisor_id=body.supervisor_id,
        name=body.name,
        blocks=[
            item.model_dump(mode="json")
            for item in body.blocks
        ],
        active=body.active,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return template_to_dict(row)


@app.get("/api/workflow-templates/active")
async def get_active_workflow_template(
    supervisor_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return template_to_dict(
        await ensure_active_template(db, supervisor_id)
    )


@app.post("/api/runs", status_code=status.HTTP_201_CREATED)
async def start_run(
    body: StartRunRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    supervisor = await db.get(Supervisor, body.supervisor_id)
    if not supervisor:
        raise HTTPException(status_code=404, detail="Supervisor not found")
    return await create_run_internal(
        supervisor=supervisor,
        order_id=body.order_id,
        request=request,
        db=db,
    )


@app.post("/api/integrations/orders", status_code=status.HTTP_201_CREATED)
async def incoming_order(
    body: IncomingOrderRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Production-style order-created endpoint for Amazon/Shopify/etc."""
    supervisor = await db.get(Supervisor, body.supervisor_id)
    if not supervisor:
        raise HTTPException(status_code=404, detail="Supervisor not found")
    return await create_run_internal(
        supervisor=supervisor,
        order_id=body.order_id,
        request=request,
        db=db,
    )


@app.get("/api/runs")
async def list_runs(
    run_status: str | None = Query(default=None, alias="status"),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    stmt = select(Run).order_by(Run.created_at.desc())
    if run_status:
        stmt = stmt.where(Run.status == run_status)

    rows = (await db.execute(stmt)).scalars().all()
    return [run_row_to_dict(row) for row in rows]


@app.get("/api/runs/{run_id}")
async def get_run(
    run_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await load_run_or_404(db, run_id)
    if row.status in TERMINAL_STATUSES:
        return await persisted_run_state(db, row)

    try:
        state = await get_handle(
            request,
            run_id,
        ).query(OrderSupervisorWorkflow.get_state)
        state["source"] = "temporal"
        return state
    except Exception:
        await db.refresh(row)
        if row.status in TERMINAL_STATUSES:
            return await persisted_run_state(db, row)
        raise


@app.get("/api/runs/{run_id}/external-state")
async def get_external_order_state(
    run_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    run = await load_run_or_404(db, run_id)
    state = await db.get(OrderRuntimeState, run.id)
    if not state:
        raise HTTPException(status_code=404, detail="External order state not found")
    return external_state_to_dict(state)


@app.patch(
    "/api/runs/{run_id}/external-state",
    status_code=status.HTTP_202_ACCEPTED,
)
async def update_external_order_state(
    run_id: str,
    body: ExternalOrderStatePatch,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    run = await ensure_signalable(db, run_id)
    state = await db.get(OrderRuntimeState, run.id)
    if not state:
        raise HTTPException(status_code=404, detail="External order state not found")

    changes = body.model_dump(exclude_none=True)
    instruction = changes.pop("instruction", None)

    if "payment_status" in changes:
        state.payment_status = changes["payment_status"]

    if "shipment_status" in changes:
        state.shipment_status = changes["shipment_status"]

    if "delivery_status" in changes:
        state.delivery_status = changes["delivery_status"]

    if "additional_delay_hours" in changes:
        state.total_delay_hours = float(state.total_delay_hours or 0.0) + float(
            changes["additional_delay_hours"]
        )
        state.shipment_status = "delayed"

    if "latest_eta" in changes:
        state.latest_eta = changes["latest_eta"]

    if "refund_status" in changes:
        if changes["refund_status"] == "requested" and state.refund_status != "requested":
            state.refund_version = int(state.refund_version or 0) + 1
        state.refund_status = changes["refund_status"]

    if "customer_message" in changes:
        state.customer_message = changes["customer_message"]
        state.customer_message_version = int(state.customer_message_version or 0) + 1

    if state.shipment_status == "delivered":
        state.delivery_status = "delivered"
    if state.delivery_status == "delivered":
        state.shipment_status = "delivered"

    await db.commit()
    await db.refresh(state)

    event_type = _event_type_for_patch(changes)
    handle = get_handle(request, run_id)
    if instruction:
        await handle.signal(OrderSupervisorWorkflow.add_instruction, instruction)
    await handle.signal(
        OrderSupervisorWorkflow.order_event,
        {
            "type": event_type,
            "payload": {
                "source": "mock_external_system",
                "changed_fields": sorted(changes.keys()),
            },
        },
    )

    return {
        "accepted": True,
        "run_id": run_id,
        "event_type": event_type,
        "state": external_state_to_dict(state),
    }


@app.post(
    "/api/runs/{run_id}/events",
    status_code=status.HTTP_202_ACCEPTED,
)
async def send_event(
    run_id: str,
    body: OrderEventRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    run = await ensure_signalable(db, run_id)
    state = await db.get(OrderRuntimeState, run.id)
    if not state:
        raise HTTPException(status_code=404, detail="External order state not found")

    # Legacy event injection also mutates the demo source of truth so timer-based
    # polling observes the same fact later.
    _apply_event_to_runtime_state(state, body.type, body.payload)
    await db.commit()

    handle = get_handle(request, run_id)

    try:
        if body.instruction:
            await handle.signal(
                OrderSupervisorWorkflow.add_instruction,
                body.instruction,
            )

        await handle.signal(
            OrderSupervisorWorkflow.order_event,
            {"type": body.type, "payload": body.payload},
        )
    except Exception as exc:
        if isinstance(exc, RPCError):
            raise temporal_http_error(exc) from exc
        raise HTTPException(
            status_code=502,
            detail=f"Could not signal workflow: {exc}",
        ) from exc

    return {
        "accepted": True,
        "run_id": run_id,
        "event_type": body.type,
        "instruction_added": bool(body.instruction),
    }


@app.post(
    "/api/runs/{run_id}/instructions",
    status_code=status.HTTP_202_ACCEPTED,
)
async def add_instruction(
    run_id: str,
    body: InstructionRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_signalable(db, run_id)
    await get_handle(request, run_id).signal(
        OrderSupervisorWorkflow.add_instruction,
        body.text,
    )
    return {"accepted": True, "run_id": run_id}


@app.post(
    "/api/runs/{run_id}/human-action",
    status_code=status.HTTP_202_ACCEPTED,
)
async def human_action(
    run_id: str,
    body: HumanActionRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_signalable(db, run_id)
    handle = get_handle(request, run_id)
    live_state = await handle.query(OrderSupervisorWorkflow.get_state)

    if not live_state.get("human_intervention_required"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This run is not currently waiting for human review",
        )

    await handle.signal(
        OrderSupervisorWorkflow.human_action,
        body.text,
    )
    return {"accepted": True, "run_id": run_id}


@app.post("/api/runs/{run_id}/interrupt")
async def interrupt_run(
    run_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_signalable(db, run_id)
    await get_handle(request, run_id).signal(
        OrderSupervisorWorkflow.interrupt_now
    )
    return {
        "accepted": True,
        "run_id": run_id,
        "status": "waiting_review",
    }


@app.post("/api/runs/{run_id}/terminate")
async def terminate_run(
    run_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_signalable(db, run_id)
    handle = get_handle(request, run_id)

    await handle.signal(OrderSupervisorWorkflow.terminate_now)

    try:
        result = await asyncio.wait_for(handle.result(), timeout=15.0)
        return {
            "accepted": True,
            "run_id": run_id,
            "workflow_execution": "completed",
            "final_state": result,
        }
    except asyncio.TimeoutError:
        return {
            "accepted": True,
            "run_id": run_id,
            "workflow_execution": "termination_signal_pending",
        }


@app.get("/api/runs/{run_id}/final-summary")
async def get_final_summary(
    run_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await load_run_or_404(db, run_id)
    summary = await db.get(FinalSummary, row.id)

    if not summary:
        raise HTTPException(
            status_code=404,
            detail="Final summary is not available yet",
        )

    return {
        "run_id": run_id,
        "summary": summary.summary,
        "actions_taken": summary.actions_taken,
        "key_learnings": summary.key_learnings,
        "recommendations": summary.recommendations,
        "created_at": summary.created_at.isoformat(),
    }