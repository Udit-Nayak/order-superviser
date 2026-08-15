import asyncio
from datetime import datetime, timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError

with workflow.unsafe.imports_passed_through():
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


@workflow.defn
class OrderSupervisorWorkflow:
    """Hybrid event + polling supervisor for one order.

    Signals give immediate wake-ups. Temporal timers provide the safety net.
    Every wake polls an external source of truth through an Activity before the
    workflow decides what the current order state means.
    """

    def __init__(self) -> None:
        self.run_id = ""
        self.order_id = ""
        self.supervisor_id = ""
        self.supervisor_config: dict[str, Any] = {}
        self.workflow_template: dict[str, Any] = {}
        self.blocks: list[dict[str, Any]] = []

        self.current_block_index = -1
        self.current_block: dict[str, Any] | None = None
        self.block_history: list[dict[str, Any]] = []

        self.timeline: list[dict[str, Any]] = []
        self.memory_summary = ""
        self.key_facts: dict[str, Any] = {}
        self.instructions: list[str] = []
        self.external_state: dict[str, Any] = {}

        self.status = "active"
        self.next_wake_at: datetime | None = None
        self.timer_purpose: str | None = None
        self.terminal = False
        self.completion_mode = "completed"
        self.human_intervention_required = False

        self._pending_events: list[dict[str, Any]] = []
        self._pending_human_actions: list[str] = []
        self._pending_instruction_records: list[dict[str, Any]] = []
        self._pending_timeline_entries: list[dict[str, Any]] = []
        self._timeline_counter = 0
        self._instruction_counter = 0

    # ------------------------------------------------------------------
    # deterministic helpers
    # ------------------------------------------------------------------

    def _now_iso(self) -> str:
        return workflow.now().isoformat()

    def _block_payload(self) -> dict[str, Any]:
        if not self.current_block:
            return {}
        return {
            "block_id": self.current_block.get("id"),
            "block_label": self.current_block.get("label"),
            "block_type": self.current_block.get("block_type"),
        }

    def _append_timeline(
        self,
        entry_type: str,
        summary: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self._timeline_counter += 1
        merged = dict(self._block_payload())
        merged.update(payload or {})
        entry = {
            "run_id": self.run_id,
            "type": entry_type,
            "summary": summary,
            "payload": merged,
            "created_at": self._now_iso(),
            "idempotency_key": f"{self.run_id}:timeline:{self._timeline_counter}",
        }
        self.timeline.append(entry)
        self._pending_timeline_entries.append(entry)

    def _public_timeline(self) -> list[dict[str, Any]]:
        return [
            {
                "type": item["type"],
                "summary": item["summary"],
                "payload": item.get("payload", {}),
                "created_at": item["created_at"],
            }
            for item in self.timeline
        ]

    def _find_block_index(self, block_type: str) -> int | None:
        for index, block in enumerate(self.blocks):
            if block.get("enabled", True) and block.get("block_type") == block_type:
                return index
        return None

    def _current_wait_seconds(self) -> int:
        if not self.current_block:
            return 30
        return max(1, int(self.current_block.get("wait_seconds", 30) or 30))

    def _schedule(self, seconds: int, purpose: str = "poll") -> None:
        self.next_wake_at = workflow.now() + timedelta(seconds=max(1, seconds))
        self.timer_purpose = purpose

    def _schedule_poll(self, decision: dict[str, Any] | None = None) -> None:
        """Schedule the Builder poll interval, optionally honoring an earlier AI wake."""
        default_target = workflow.now() + timedelta(seconds=self._current_wait_seconds())
        chosen = default_target

        value = (decision or {}).get("next_wake_at")
        if value:
            try:
                parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                if parsed > workflow.now() and parsed < chosen:
                    chosen = parsed
            except ValueError:
                self._append_timeline(
                    "system",
                    "Agent returned an invalid next wake; Builder polling interval retained.",
                    {"agent_next_wake_at": value},
                )

        self.next_wake_at = chosen
        self.timer_purpose = "poll"

    # ------------------------------------------------------------------
    # persistence activities
    # ------------------------------------------------------------------

    async def _flush_timeline(self) -> None:
        while self._pending_timeline_entries:
            entry = self._pending_timeline_entries.pop(0)
            await workflow.execute_activity(
                persist_timeline_activity,
                entry,
                start_to_close_timeout=timedelta(seconds=15),
            )

    async def _flush_instructions(self) -> None:
        while self._pending_instruction_records:
            record = self._pending_instruction_records.pop(0)
            await workflow.execute_activity(
                persist_instruction_activity,
                record,
                start_to_close_timeout=timedelta(seconds=15),
            )

    async def _persist_status(self) -> None:
        await workflow.execute_activity(
            persist_run_status_activity,
            {
                "run_id": self.run_id,
                "status": self.status,
                "next_wake_at": self.next_wake_at.isoformat()
                if self.next_wake_at
                else None,
            },
            start_to_close_timeout=timedelta(seconds=15),
        )

    async def _persist_memory(self) -> None:
        await workflow.execute_activity(
            persist_memory_activity,
            {
                "run_id": self.run_id,
                "summary": self.memory_summary,
                "key_facts": self.key_facts,
            },
            start_to_close_timeout=timedelta(seconds=15),
        )

    # ------------------------------------------------------------------
    # block transitions
    # ------------------------------------------------------------------

    async def _enter_block(self, index: int) -> None:
        if index < 0 or index >= len(self.blocks):
            self.current_block_index = -1
            self.current_block = None
            return

        self.current_block_index = index
        self.current_block = dict(self.blocks[index])
        self._append_timeline(
            "workflow_block",
            f"Entered workflow block: {self.current_block.get('label')}",
            {
                "state": "entered",
                "block_instruction": self.current_block.get("instruction", ""),
                "wait_seconds": self.current_block.get("wait_seconds", 0),
            },
        )
        await self._flush_timeline()

        if self.current_block.get("block_type") == "post_delivery":
            # After delivery we stop recurring external-state polling.
            # This is a one-shot inactivity/support-window timeout. Incoming
            # customer/refund signals can still wake the workflow immediately.
            self.status = "post_delivery"
            self._schedule(
                self._current_wait_seconds(),
                "post_delivery_support_timeout",
            )
        else:
            self.status = "sleeping"
            self._schedule(self._current_wait_seconds(), "poll")
        await self._persist_status()

    async def _complete_current_block(self, reason: str) -> None:
        if not self.current_block:
            return
        item = {
            "id": self.current_block.get("id"),
            "label": self.current_block.get("label"),
            "block_type": self.current_block.get("block_type"),
            "completed_at": self._now_iso(),
            "reason": reason,
        }
        self.block_history.append(item)
        self._append_timeline(
            "workflow_block",
            f"Completed workflow block: {self.current_block.get('label')}",
            {"state": "completed", "reason": reason},
        )
        await self._flush_timeline()

    async def _advance(self, reason: str) -> None:
        await self._complete_current_block(reason)
        next_index = self.current_block_index + 1
        while next_index < len(self.blocks) and not self.blocks[next_index].get("enabled", True):
            next_index += 1

        if next_index >= len(self.blocks):
            self.current_block_index = -1
            self.current_block = None
            self.terminal = True
            self.next_wake_at = None
            self.timer_purpose = None
            return
        await self._enter_block(next_index)

    async def _jump_to(self, block_type: str, reason: str) -> bool:
        index = self._find_block_index(block_type)
        if index is None:
            return False
        if self.current_block and self.current_block_index != index:
            await self._complete_current_block(reason)
        await self._enter_block(index)
        return True

    # ------------------------------------------------------------------
    # external state + agent + tools
    # ------------------------------------------------------------------

    async def _poll_external_state(self, trigger: str) -> dict[str, Any]:
        state = await workflow.execute_activity(
            get_order_state_activity,
            {"run_id": self.run_id},
            start_to_close_timeout=timedelta(seconds=15),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=1),
                maximum_interval=timedelta(seconds=5),
                maximum_attempts=4,
            ),
        )
        self.external_state = state
        self._append_timeline(
            "state_poll",
            f"Polled external order state ({trigger}).",
            {
                "trigger": trigger,
                "payment_status": state.get("payment_status"),
                "shipment_status": state.get("shipment_status"),
                "delivery_status": state.get("delivery_status"),
                "total_delay_hours": state.get("total_delay_hours", 0),
                "refund_status": state.get("refund_status"),
            },
        )
        await self._flush_timeline()
        return state

    async def _execute_tool(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        result = await workflow.execute_activity(
            execute_tool_activity,
            {
                "run_id": self.run_id,
                "order_id": self.order_id,
                "tool": tool,
                "args": args,
            },
            start_to_close_timeout=timedelta(seconds=15),
        )
        self._append_timeline(
            "tool_call",
            result["summary"],
            {
                "tool": result["tool"],
                "args": result.get("args", {}),
                "ok": result.get("ok", True),
            },
        )
        await self._flush_timeline()
        return result

    async def _run_agent(
        self,
        *,
        trigger: str,
        event: dict[str, Any] | None,
        state: dict[str, Any],
        already_executed_actions: list[str] | None = None,
    ) -> dict[str, Any]:
        self.status = "thinking"
        self.next_wake_at = None
        await self._persist_status()

        context = {
            "run_id": self.run_id,
            "order_id": self.order_id,
            "trigger": trigger,
            "event": event,
            "external_state": state,
            "already_executed_actions": already_executed_actions or [],
            "supervisor_config": self.supervisor_config,
            "instructions": list(self.instructions),
            "memory_summary": self.memory_summary,
            "key_facts": dict(self.key_facts),
            "timeline": self._public_timeline()[-20:],
            "default_wake_seconds": self._current_wait_seconds(),
            "current_block": dict(self.current_block) if self.current_block else None,
            "block_instruction": self.current_block.get("instruction", "")
            if self.current_block
            else "",
        }

        try:
            decision = await workflow.execute_activity(
                run_agent_activity,
                context,
                start_to_close_timeout=timedelta(seconds=60),
                retry_policy=RetryPolicy(
                    initial_interval=timedelta(seconds=2),
                    maximum_interval=timedelta(seconds=15),
                    maximum_attempts=4,
                ),
            )
        except ActivityError:
            decision = {
                "reasoning": "Gemini unavailable after retries; deterministic monitoring continued.",
                "actions": [],
                "memory_update": {
                    "summary": self.memory_summary,
                    "key_facts": dict(self.key_facts),
                },
                "next_wake_at": (
                    workflow.now() + timedelta(seconds=self._current_wait_seconds())
                ).isoformat(),
                "close_workflow": False,
                "warnings": [
                    "Gemini activity failed after retries; workflow stayed alive and will poll again."
                ],
                "fallback": True,
            }

        memory_update = decision.get("memory_update") or {}
        self.memory_summary = memory_update.get("summary", self.memory_summary)
        for key, value in (memory_update.get("key_facts") or {}).items():
            if value is not None:
                self.key_facts[key] = value

        for warning in decision.get("warnings", []):
            self._append_timeline(
                "system",
                warning,
                {"kind": "agent_warning", "trigger": trigger},
            )

        self._append_timeline(
            "agent_decision",
            f"Agent reviewed the order after '{trigger}' and proposed {len(decision.get('actions', []))} additional action(s).",
            {
                "trigger": trigger,
                "event": event,
                "reasoning": decision.get("reasoning", ""),
                "fallback": bool(decision.get("fallback", False)),
            },
        )

        for action in decision.get("actions", []):
            await self._execute_tool(action["tool"], action.get("args", {}))

        await self._persist_memory()
        await self._flush_timeline()
        return decision

    async def _monitor_again(self, decision: dict[str, Any] | None = None) -> None:
        self.human_intervention_required = False

        if self.current_block and self.current_block.get("block_type") == "post_delivery":
            # Post-delivery is event-driven. We only keep one inactivity
            # timeout which is restarted after each handled support event.
            self.status = "post_delivery"
            self._schedule(
                self._current_wait_seconds(),
                "post_delivery_support_timeout",
            )
        else:
            self.status = "sleeping"
            self._schedule_poll(decision)

        await self._persist_status()

    async def _require_human(self, reason: str) -> None:
        self.human_intervention_required = True
        self.status = "waiting_review"
        self.next_wake_at = None
        self.timer_purpose = None
        self._append_timeline(
            "system",
            reason,
            {"human_intervention_required": True},
        )
        await self._flush_timeline()
        await self._persist_status()

    # ------------------------------------------------------------------
    # deterministic state evaluation
    # ------------------------------------------------------------------

    async def _evaluate_payment(
        self,
        trigger: str,
        event: dict[str, Any] | None,
        state: dict[str, Any],
    ) -> None:
        payment = state.get("payment_status", "pending")

        if payment == "confirmed":
            self.key_facts["payment_confirmed"] = True
            self.key_facts["payment_failure_checks"] = 0
            self.memory_summary = f"Payment confirmed for {self.order_id}; waiting for shipment creation."
            await self._persist_memory()
            decision = await self._run_agent(trigger=trigger, event=event, state=state)
            shipment_index = self._find_block_index("shipment")
            if shipment_index is not None:
                self.human_intervention_required = False
                await self._complete_current_block("external payment state confirmed")
                await self._enter_block(shipment_index)

                # If the warehouse/courier state arrived early, do not wait for
                # another timer just because the payment block was active.
                if state.get("shipment_status") in {
                    "created",
                    "in_transit",
                    "delayed",
                    "delivered",
                }:
                    await self._evaluate_shipment(trigger, event, state)
            else:
                await self._monitor_again(decision)
            return

        if payment == "failed":
            checks = int(self.key_facts.get("payment_failure_checks", 0)) + 1
            self.key_facts["payment_failure_checks"] = checks
            self.memory_summary = (
                f"Payment is still failed for {self.order_id}. "
                f"The supervisor has observed {checks} failed check(s)."
            )
            await self._persist_memory()

            settings = (self.current_block or {}).get("settings") or {}
            notify_after = int(settings.get("notify_after_failures", 2))
            human_after = int(settings.get("human_after_failures", 3))
            executed: list[str] = []

            if checks == notify_after:
                await self._execute_tool(
                    "message_payments_team",
                    {
                        "message": (
                            f"Payment for {self.order_id} is still failing after "
                            f"{checks} supervisor checks."
                        )
                    },
                )
                executed.append("message_payments_team")

            if checks >= human_after:
                if checks == human_after:
                    await self._execute_tool(
                        "message_payments_team",
                        {
                            "message": (
                                f"Payment for {self.order_id} failed through the "
                                f"configured {checks}-check threshold. Human handling is required."
                            )
                        },
                    )
                    executed.append("message_payments_team")
                    await self._execute_tool(
                        "create_internal_note",
                        {
                            "note": (
                                f"Payment monitoring reached human review after "
                                f"{checks} consecutive failed observations."
                            )
                        },
                    )
                    executed.append("create_internal_note")

                await self._run_agent(
                    trigger=trigger,
                    event=event,
                    state=state,
                    already_executed_actions=executed,
                )
                await self._require_human(
                    f"Payment is still failed after {checks} checks; waiting for a human decision."
                )
                return

            decision = await self._run_agent(
                trigger=trigger,
                event=event,
                state=state,
                already_executed_actions=executed,
            )
            await self._monitor_again(decision)
            return

        # pending payment
        self.memory_summary = f"Order {self.order_id} is waiting for payment confirmation."
        await self._persist_memory()
        decision = await self._run_agent(trigger=trigger, event=event, state=state)
        await self._monitor_again(decision)

    async def _evaluate_shipment(
        self,
        trigger: str,
        event: dict[str, Any] | None,
        state: dict[str, Any],
    ) -> None:
        shipment = state.get("shipment_status", "not_created")

        if state.get("delivery_status") == "delivered" or shipment == "delivered":
            await self._handle_delivery(trigger, event, state)
            return

        if shipment in {"created", "in_transit", "delayed"}:
            self.key_facts["shipment_created"] = True
            self.memory_summary = f"Shipment exists for {self.order_id}; monitoring transit."
            await self._persist_memory()
            decision = await self._run_agent(trigger=trigger, event=event, state=state)
            transit_index = self._find_block_index("in_transit")
            if transit_index is not None:
                await self._complete_current_block("external shipment state is created/in transit")
                await self._enter_block(transit_index)
                if shipment == "delayed":
                    # Process an already-present delay immediately in the new block.
                    await self._evaluate_in_transit(trigger, event, state)
            else:
                await self._monitor_again(decision)
            return

        # not created: only scheduled polls count as overdue checks.
        overdue_checks = int(self.key_facts.get("shipment_missing_checks", 0))
        executed: list[str] = []
        if trigger == "scheduled_wake":
            overdue_checks += 1
            self.key_facts["shipment_missing_checks"] = overdue_checks
            if overdue_checks == 1 and bool(
                ((self.current_block or {}).get("settings") or {}).get(
                    "notify_fulfillment_when_overdue", True
                )
            ):
                await self._execute_tool(
                    "message_fulfillment_team",
                    {
                        "message": (
                            f"Shipment for {self.order_id} was not created by the "
                            f"configured {self._current_wait_seconds()}-second check."
                        )
                    },
                )
                executed.append("message_fulfillment_team")

        self.memory_summary = (
            f"Payment is complete but shipment for {self.order_id} has not been created yet."
        )
        await self._persist_memory()
        decision = await self._run_agent(
            trigger=trigger,
            event=event,
            state=state,
            already_executed_actions=executed,
        )
        await self._monitor_again(decision)

    async def _evaluate_in_transit(
        self,
        trigger: str,
        event: dict[str, Any] | None,
        state: dict[str, Any],
    ) -> None:
        shipment = state.get("shipment_status")
        if state.get("delivery_status") == "delivered" or shipment == "delivered":
            await self._handle_delivery(trigger, event, state)
            return

        current_delay = float(state.get("total_delay_hours") or 0.0)
        notified_delay = float(self.key_facts.get("last_notified_delay_hours", 0.0))
        new_delay = current_delay > notified_delay
        executed: list[str] = []

        if new_delay:
            delta = current_delay - notified_delay
            eta_text = (
                f" New estimated delivery time: {state.get('latest_eta')}."
                if state.get("latest_eta")
                else ""
            )
            await self._execute_tool(
                "message_customer",
                {
                    "message": (
                        f"Your order {self.order_id} has an additional shipping delay "
                        f"of {delta:g} hour(s). Total delay is now {current_delay:g} hour(s)."
                        f"{eta_text}"
                    )
                },
            )
            executed.append("message_customer")
            await self._execute_tool(
                "message_logistics_team",
                {
                    "message": (
                        f"{self.order_id}: new delay +{delta:g}h; cumulative delay "
                        f"{current_delay:g}h. Latest ETA: {state.get('latest_eta') or 'not supplied'}."
                    )
                },
            )
            executed.append("message_logistics_team")
            self.key_facts["last_notified_delay_hours"] = current_delay
            self.memory_summary = (
                f"Shipment for {self.order_id} has {current_delay:g} total hours of reported delay."
            )
            await self._persist_memory()

        decision = await self._run_agent(
            trigger=trigger,
            event=event,
            state=state,
            already_executed_actions=executed,
        )

        human_on_delay = bool(
            ((self.current_block or {}).get("settings") or {}).get("human_on_new_delay", True)
        )
        if new_delay and human_on_delay:
            await self._require_human(
                f"A new shipment delay was reported. Cumulative delay is {current_delay:g} hour(s)."
            )
            return

        await self._monitor_again(decision)

    async def _handle_delivery(
        self,
        trigger: str,
        event: dict[str, Any] | None,
        state: dict[str, Any],
    ) -> None:
        # Delivery is a deterministic resolving fact; an older review state
        # must not prevent the workflow from progressing to post-delivery.
        self.human_intervention_required = False

        if not self.key_facts.get("delivery_notifications_sent"):
            await self._execute_tool(
                "message_customer",
                {"message": f"Your order {self.order_id} has been delivered successfully."},
            )
            await self._execute_tool(
                "message_fulfillment_team",
                {"message": f"Order {self.order_id} is confirmed delivered."},
            )
            self.key_facts["delivery_notifications_sent"] = True

        self.key_facts["delivered"] = True
        self.memory_summary = f"Order {self.order_id} is delivered. Monitoring post-delivery support."
        await self._persist_memory()
        await self._run_agent(
            trigger=trigger,
            event=event,
            state=state,
            already_executed_actions=["message_customer", "message_fulfillment_team"],
        )

        delivered_index = self._find_block_index("delivered")
        if delivered_index is not None and self.current_block_index != delivered_index:
            await self._complete_current_block("external delivery confirmed")
            await self._enter_block(delivered_index)

        post_index = self._find_block_index("post_delivery")
        if post_index is None:
            self.terminal = True
            self.next_wake_at = None
            self.timer_purpose = None
            return

        if self.current_block and self.current_block.get("block_type") == "delivered":
            await self._complete_current_block("delivery notifications completed")
        await self._enter_block(post_index)

    async def _evaluate_post_delivery(
        self,
        trigger: str,
        event: dict[str, Any] | None,
        state: dict[str, Any],
    ) -> None:
        refund_version = int(state.get("refund_version") or 0)
        processed_refund_version = int(self.key_facts.get("processed_refund_version", 0))

        if state.get("refund_status") == "requested" and refund_version > processed_refund_version:
            self.key_facts["processed_refund_version"] = refund_version
            await self._execute_tool(
                "message_payments_team",
                {"message": f"Refund requested for delivered order {self.order_id}. Human review required."},
            )
            await self._run_agent(
                trigger=trigger,
                event=event,
                state=state,
                already_executed_actions=["message_payments_team"],
            )
            await self._require_human("A new refund request requires a human decision.")
            return

        message_version = int(state.get("customer_message_version") or 0)
        processed_message_version = int(self.key_facts.get("processed_customer_message_version", 0))
        if message_version > processed_message_version:
            self.key_facts["processed_customer_message_version"] = message_version
            self.memory_summary = (
                f"A post-delivery customer message was received for {self.order_id}: "
                f"{state.get('customer_message') or ''}"
            )
            await self._persist_memory()
            decision = await self._run_agent(trigger=trigger, event=event, state=state)
            await self._monitor_again(decision)
            return

        # No recurring post-delivery polling. This method is reached because
        # an actual support/refund signal arrived, so handle it and restart the
        # inactivity support window.
        decision = await self._run_agent(trigger=trigger, event=event, state=state)
        await self._monitor_again(decision)

    async def _evaluate_state(
        self,
        *,
        trigger: str,
        event: dict[str, Any] | None,
    ) -> None:
        state = await self._poll_external_state(trigger)
        block_type = self.current_block.get("block_type") if self.current_block else None

        if state.get("delivery_status") == "delivered" and block_type != "post_delivery":
            await self._handle_delivery(trigger, event, state)
            return

        if block_type == "payment":
            await self._evaluate_payment(trigger, event, state)
        elif block_type == "shipment":
            await self._evaluate_shipment(trigger, event, state)
        elif block_type == "in_transit":
            await self._evaluate_in_transit(trigger, event, state)
        elif block_type == "delivered":
            await self._handle_delivery(trigger, event, state)
        elif block_type == "post_delivery":
            await self._evaluate_post_delivery(trigger, event, state)
        else:
            decision = await self._run_agent(trigger=trigger, event=event, state=state)
            await self._monitor_again(decision)

    # ------------------------------------------------------------------
    # human handling
    # ------------------------------------------------------------------

    async def _handle_human_action(self, text: str) -> None:
        self.human_intervention_required = False
        self._append_timeline(
            "human_action",
            "Human operator handled the case.",
            {"text": text},
        )

        self.instructions.append(text)
        self._instruction_counter += 1
        self._pending_instruction_records.append(
            {
                "run_id": self.run_id,
                "text": text,
                "created_at": self._now_iso(),
                "idempotency_key": f"{self.run_id}:instruction:{self._instruction_counter}",
            }
        )
        await self._flush_instructions()
        await self._flush_timeline()

        state = await self._poll_external_state("human_action")
        await self._run_agent(
            trigger="human_action",
            event={"type": "human_action", "payload": {"text": text}},
            state=state,
        )

        lower = text.lower()
        if any(phrase in lower for phrase in {"cancel order", "close order", "terminate"}):
            self.terminal = True
            self.completion_mode = "terminated"
            self.next_wake_at = None
            self.timer_purpose = None
            return

        if self.current_block and self.current_block.get("block_type") == "payment" and "retry" in lower:
            # Give a human-requested retry a fresh monitoring window.
            self.key_facts["payment_failure_checks"] = 0
            await self._persist_memory()

        await self._monitor_again()

    # ------------------------------------------------------------------
    # durable wait loop
    # ------------------------------------------------------------------

    async def _wait_for_work(self) -> str:
        if self.terminal:
            return "terminate"
        if self._pending_human_actions:
            return "human_action"
        if self._pending_instruction_records:
            return "instruction"
        if self._pending_events:
            return "event"

        if self.human_intervention_required:
            self.status = "waiting_review"
            self.next_wake_at = None
            self.timer_purpose = None
            await self._persist_status()

            # Human review stops scheduled polling, but important external
            # signals still wake the workflow. Example: payment may succeed
            # while an operator is looking at a repeated-payment-failure case.
            await workflow.wait_condition(
                lambda: bool(self._pending_human_actions)
                or bool(self._pending_events)
                or bool(self._pending_instruction_records)
                or self.terminal
            )

            if self.terminal:
                return "terminate"
            if self._pending_human_actions:
                return "human_action"
            if self._pending_instruction_records:
                return "instruction"
            return "event"

        if self.next_wake_at is None:
            if self.current_block and self.current_block.get("block_type") == "post_delivery":
                self.status = "post_delivery"
                self._schedule(
                    self._current_wait_seconds(),
                    "post_delivery_support_timeout",
                )
            else:
                self.status = "sleeping"
                self._schedule(self._current_wait_seconds(), "poll")
            await self._persist_status()

        remaining = (self.next_wake_at - workflow.now()).total_seconds()
        if remaining <= 0:
            return "timer"

        signal_task = asyncio.create_task(
            workflow.wait_condition(
                lambda: bool(self._pending_events)
                or bool(self._pending_human_actions)
                or bool(self._pending_instruction_records)
                or self.terminal
            )
        )
        timer_task = asyncio.create_task(workflow.sleep(remaining))

        done, pending = await workflow.wait(
            {signal_task, timer_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

        if self.terminal:
            return "terminate"
        if self._pending_human_actions:
            return "human_action"
        if self._pending_instruction_records:
            return "instruction"
        if self._pending_events:
            return "event"
        if timer_task in done:
            return "timer"
        return "event"

    # ------------------------------------------------------------------
    # finalization
    # ------------------------------------------------------------------

    async def _finalize(self) -> dict[str, Any]:
        self.next_wake_at = None
        self.timer_purpose = None
        await self._flush_instructions()
        await self._flush_timeline()

        try:
            final_summary = await workflow.execute_activity(
                run_final_summary_activity,
                {
                    "run_id": self.run_id,
                    "order_id": self.order_id,
                    "supervisor_config": self.supervisor_config,
                    "instructions": list(self.instructions),
                    "memory_summary": self.memory_summary,
                    "key_facts": dict(self.key_facts),
                    "timeline": self._public_timeline(),
                },
                start_to_close_timeout=timedelta(seconds=60),
                retry_policy=RetryPolicy(
                    initial_interval=timedelta(seconds=2),
                    maximum_interval=timedelta(seconds=15),
                    maximum_attempts=4,
                ),
            )
        except ActivityError:
            final_summary = {
                "summary": self.memory_summary or f"Order supervisor run for {self.order_id} ended.",
                "actions_taken": [
                    item["summary"] for item in self.timeline if item.get("type") == "tool_call"
                ],
                "key_learnings": [
                    "Gemini final summary was unavailable; deterministic fallback was persisted."
                ],
                "recommendations": ["Review the execution logs for full operational detail."],
            }

        await workflow.execute_activity(
            persist_final_summary_activity,
            {"run_id": self.run_id, **final_summary},
            start_to_close_timeout=timedelta(seconds=15),
        )
        self.status = self.completion_mode
        await self._persist_status()
        return self.get_state()

    # ------------------------------------------------------------------
    # Temporal entry point + signals/query
    # ------------------------------------------------------------------

    @workflow.run
    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        self.run_id = input_data["run_id"]
        self.order_id = input_data["order_id"]
        self.supervisor_id = str(input_data.get("supervisor_id", ""))
        self.supervisor_config = input_data.get("supervisor_config", {})
        self.workflow_template = input_data.get("workflow_template", {})
        self.blocks = list(self.workflow_template.get("blocks") or [])

        self._append_timeline(
            "event",
            f"Order created: {self.order_id}",
            {"event_type": "order_created", "source": "run_start"},
        )
        await self._flush_timeline()

        if not self.blocks:
            self.terminal = True
            self.completion_mode = "failed"
            return await self._finalize()

        first_index = next(
            (i for i, block in enumerate(self.blocks) if block.get("enabled", True)),
            0,
        )
        await self._enter_block(first_index)

        if self.current_block and self.current_block.get("block_type") == "order_created":
            state = await self._poll_external_state("workflow_start")
            await self._run_agent(
                trigger="workflow_start",
                event={"type": "order_created", "payload": {}},
                state=state,
            )
            await self._advance("order monitoring started")

        while not self.terminal:
            reason = await self._wait_for_work()

            if reason == "terminate":
                break

            if reason == "instruction":
                await self._flush_instructions()
                await self._flush_timeline()
                continue

            if reason == "human_action":
                await self._handle_human_action(self._pending_human_actions.pop(0))
                continue

            if reason == "event":
                batch = list(self._pending_events)
                self._pending_events.clear()
                await self._flush_timeline()
                for event in batch:
                    if self.terminal:
                        break
                    classification = await workflow.execute_activity(
                        classify_event_activity,
                        {"event": event},
                        start_to_close_timeout=timedelta(seconds=10),
                    )
                    self._append_timeline(
                        "system",
                        f"Classifier: {classification['event_type']} -> {'WAKE' if classification['important'] else 'LOG ONLY'}",
                        classification,
                    )
                    await self._flush_timeline()
                    if classification["important"]:
                        self.next_wake_at = None
                        self.timer_purpose = None
                        await self._evaluate_state(trigger="signal", event=event)
                continue

            if reason == "timer":
                scheduled_for = (
                    self.next_wake_at.isoformat()
                    if self.next_wake_at
                    else None
                )
                purpose = self.timer_purpose
                self.next_wake_at = None
                self.timer_purpose = None

                if purpose == "post_delivery_support_timeout":
                    # One-shot completion timer. Critically, DO NOT call
                    # get_order_state_activity here: after confirmed delivery
                    # the workflow is event-driven and waits only for support
                    # signals or this inactivity timeout.
                    self._append_timeline(
                        "system",
                        "Post-delivery support window expired with no unresolved human review.",
                        {
                            "scheduled_for": scheduled_for,
                            "timer_purpose": purpose,
                        },
                    )
                    await self._flush_timeline()
                    self.terminal = True
                    continue

                self._append_timeline(
                    "system",
                    "Scheduled polling wake fired.",
                    {
                        "scheduled_for": scheduled_for,
                        "timer_purpose": purpose,
                    },
                )
                await self._flush_timeline()
                await self._evaluate_state(
                    trigger="scheduled_wake",
                    event=None,
                )
                continue

        if self.completion_mode == "terminated":
            self._append_timeline("system", "Workflow terminated by operator.", {})
            await self._flush_timeline()
        return await self._finalize()

    @workflow.signal
    def order_event(self, event: dict[str, Any]) -> None:
        self._pending_events.append(event)
        self._append_timeline(
            "event",
            f"Received external order event: {event.get('type', 'unknown')}",
            event,
        )

    @workflow.signal
    def add_instruction(self, text: str) -> None:
        self.instructions.append(text)
        self._instruction_counter += 1
        self._pending_instruction_records.append(
            {
                "run_id": self.run_id,
                "text": text,
                "created_at": self._now_iso(),
                "idempotency_key": f"{self.run_id}:instruction:{self._instruction_counter}",
            }
        )
        self._append_timeline(
            "instruction",
            "Run-specific instruction added.",
            {"text": text},
        )

    @workflow.signal
    def human_action(self, text: str) -> None:
        self._pending_human_actions.append(text)

    @workflow.signal
    def interrupt_now(self) -> None:
        if not self.terminal:
            self.human_intervention_required = True
            self.status = "waiting_review"
            self.next_wake_at = None
            self.timer_purpose = None
            self._append_timeline(
                "system",
                "Automation interrupted by operator; human control requested.",
                {"human_intervention_required": True},
            )

    @workflow.signal
    def terminate_now(self) -> None:
        if not self.terminal:
            self.terminal = True
            self.completion_mode = "terminated"
            self.status = "terminated"
            self.next_wake_at = None
            self.timer_purpose = None

    @workflow.query
    def get_state(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "order_id": self.order_id,
            "supervisor_id": self.supervisor_id,
            "status": self.status,
            "timeline": self._public_timeline(),
            "memory_summary": self.memory_summary,
            "key_facts": dict(self.key_facts),
            "instructions": list(self.instructions),
            "external_state": dict(self.external_state),
            "next_wake_at": self.next_wake_at.isoformat() if self.next_wake_at else None,
            "terminal": self.terminal,
            "pending_event_count": len(self._pending_events),
            "human_intervention_required": self.human_intervention_required,
            "current_block": dict(self.current_block) if self.current_block else None,
            "block_history": list(self.block_history),
            "workflow_template_name": self.workflow_template.get("name", ""),
        }
