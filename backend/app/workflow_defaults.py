from typing import Any


def default_workflow_blocks() -> list[dict[str, Any]]:
    """Demo-friendly hybrid event + polling workflow.

    wait_seconds now means: if no external event arrives earlier, poll the
    external order state again after this many seconds.
    """
    return [
        {
            "id": "order-created",
            "block_type": "order_created",
            "label": "Order created",
            "wait_seconds": 0,
            "instruction": (
                "Start monitoring the order and establish compact memory. "
                "The workflow will move immediately to payment monitoring."
            ),
            "settings": {},
        },
        {
            "id": "payment",
            "block_type": "payment",
            "label": "Payment monitoring",
            "wait_seconds": 10,
            "instruction": (
                "Monitor payment state. External payment updates wake immediately; "
                "otherwise poll again every configured interval. Repeated failed "
                "checks should notify payments and eventually request human review."
            ),
            "settings": {
                "notify_after_failures": 2,
                "human_after_failures": 3,
            },
        },
        {
            "id": "shipment",
            "block_type": "shipment",
            "label": "Shipment creation",
            "wait_seconds": 10,
            "instruction": (
                "Monitor whether fulfillment has created the shipment. A shipment "
                "event wakes immediately; otherwise poll on the configured interval."
            ),
            "settings": {"notify_fulfillment_when_overdue": True},
        },
        {
            "id": "in-transit",
            "block_type": "in_transit",
            "label": "In transit / delay monitoring",
            "wait_seconds": 15,
            "instruction": (
                "Monitor the courier state. New delay totals should notify the customer "
                "and logistics, then allow human review. Do not re-notify the same delay."
            ),
            "settings": {"human_on_new_delay": True},
        },
        {
            "id": "delivered",
            "block_type": "delivered",
            "label": "Delivered",
            "wait_seconds": 0,
            "instruction": (
                "On confirmed delivery, notify the customer and fulfillment, then move "
                "to the post-delivery support window if that block exists."
            ),
            "settings": {},
        },
        {
            "id": "post-delivery",
            "block_type": "post_delivery",
            "label": "Post-delivery support",
            "wait_seconds": 30,
            "instruction": (
                "After confirmed delivery, stop recurring order-state polling. Wait only "
                "for customer-message/refund signals or this one-shot support-window "
                "timeout. Each handled support event restarts the window. When the window "
                "expires with no unresolved human review, finalize the workflow."
            ),
            "settings": {},
        },
    ]
