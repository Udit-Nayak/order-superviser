from uuid import UUID

from temporalio import activity

from app.database import AsyncSessionLocal
from app.models import OrderRuntimeState


def _to_dict(row: OrderRuntimeState) -> dict:
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


@activity.defn
async def get_order_state_activity(data: dict) -> dict:
    """Poll the demo external-system source of truth.

    Replace this Activity's implementation with real Amazon/payment/warehouse/
    courier API calls in production. Temporal orchestration does not change.
    """
    run_id = UUID(data["run_id"])
    async with AsyncSessionLocal() as session:
        row = await session.get(OrderRuntimeState, run_id)
        if row is None:
            raise RuntimeError(f"External order state missing for run {run_id}")
        return _to_dict(row)
