from datetime import datetime, timezone
from uuid import UUID, NAMESPACE_URL, uuid5

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert
from temporalio import activity

from app.database import AsyncSessionLocal
from app.models import FinalSummary, Instruction, MemorySnapshot, Run, TimelineEntry


def _stable_uuid(idempotency_key: str) -> UUID:
    return uuid5(NAMESPACE_URL, idempotency_key)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


@activity.defn
async def persist_timeline_activity(entry: dict) -> dict:
    entry_id = _stable_uuid(entry["idempotency_key"])
    async with AsyncSessionLocal() as session:
        stmt = (
            insert(TimelineEntry)
            .values(
                id=entry_id,
                run_id=UUID(entry["run_id"]),
                type=entry["type"],
                payload=entry.get("payload", {}),
                summary=entry["summary"],
                created_at=_parse_dt(entry["created_at"]),
            )
            .on_conflict_do_nothing(index_elements=[TimelineEntry.id])
        )
        await session.execute(stmt)
        await session.commit()
    return {"persisted": True, "timeline_id": str(entry_id)}


@activity.defn
async def persist_memory_activity(memory: dict) -> dict:
    run_id = UUID(memory["run_id"])
    async with AsyncSessionLocal() as session:
        stmt = insert(MemorySnapshot).values(
            run_id=run_id,
            summary=memory.get("summary", ""),
            key_facts=memory.get("key_facts", {}),
            updated_at=datetime.now(timezone.utc),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[MemorySnapshot.run_id],
            set_={
                "summary": stmt.excluded.summary,
                "key_facts": stmt.excluded.key_facts,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        await session.execute(stmt)
        await session.commit()
    return {"persisted": True, "run_id": str(run_id)}


@activity.defn
async def persist_run_status_activity(data: dict) -> dict:
    run_id = UUID(data["run_id"])
    status = data["status"]
    values = {
        "status": status,
        "next_wake_at": _parse_dt(data.get("next_wake_at")),
        "updated_at": datetime.now(timezone.utc),
    }
    if status in {"completed", "terminated", "failed"}:
        values["completed_at"] = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as session:
        await session.execute(update(Run).where(Run.id == run_id).values(**values))
        await session.commit()
    return {"persisted": True, "run_id": str(run_id), "status": status}


@activity.defn
async def persist_instruction_activity(data: dict) -> dict:
    instruction_id = _stable_uuid(data["idempotency_key"])
    async with AsyncSessionLocal() as session:
        stmt = (
            insert(Instruction)
            .values(
                id=instruction_id,
                run_id=UUID(data["run_id"]),
                text=data["text"],
                active=True,
                created_at=_parse_dt(data["created_at"]),
            )
            .on_conflict_do_nothing(index_elements=[Instruction.id])
        )
        await session.execute(stmt)
        await session.commit()
    return {"persisted": True, "instruction_id": str(instruction_id)}


@activity.defn
async def persist_final_summary_activity(data: dict) -> dict:
    run_id = UUID(data["run_id"])
    async with AsyncSessionLocal() as session:
        stmt = insert(FinalSummary).values(
            run_id=run_id,
            summary=data["summary"],
            actions_taken=data.get("actions_taken", []),
            key_learnings=data.get("key_learnings", []),
            recommendations=data.get("recommendations", []),
            created_at=datetime.now(timezone.utc),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[FinalSummary.run_id],
            set_={
                "summary": stmt.excluded.summary,
                "actions_taken": stmt.excluded.actions_taken,
                "key_learnings": stmt.excluded.key_learnings,
                "recommendations": stmt.excluded.recommendations,
                "created_at": stmt.excluded.created_at,
            },
        )
        await session.execute(stmt)
        await session.commit()
    return {"persisted": True, "run_id": str(run_id)}
