# Walkthrough Video Checklist

This document is a recording guide for the final Order Supervisor walkthrough.

The goal is to demonstrate every required deliverable clearly without spending too much time on internal implementation details.

---

# 1. Before Recording

Start all services.

### Terminal 1 — Temporal

```powershell
temporal server start-dev --db-filename "$HOME\temporal-order-supervisor-final-demo.db"
```

### Terminal 2 — Worker

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m app.worker
```

### Terminal 3 — FastAPI

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

### Terminal 4 — Next.js

```powershell
cd frontend
npm run dev
```

Open:

```text
Dashboard:    http://localhost:3000
Temporal UI:  http://localhost:8233
FastAPI docs: http://localhost:8000/docs
```

For a short demo, configure:

```text
Payment poll:               10 seconds
Shipment poll:              10 seconds
In-transit poll:            10 seconds
Post-delivery support:      30 seconds
```

Use a completely fresh order ID.

Example:

```text
ORDER-FINAL-DEMO-001
```

---

# 2. Opening Explanation

Suggested explanation:

> This project is an AI Order Supervisor built using Next.js, FastAPI, Temporal, Gemini, and Supabase. Each order gets its own durable Temporal workflow. The workflow uses a hybrid monitoring model: external changes wake it immediately through Signals, while Temporal timers independently poll the latest order state if no event arrives.

Keep this introduction to approximately 20–30 seconds.

---

# 3. Create Supervisor Configuration

Open:

```text
Setup
```

Show:

- supervisor name,
- base instruction,
- enabled business actions.

Mention the five available business actions:

```text
message_fulfillment_team
message_payments_team
message_logistics_team
message_customer
create_internal_note
```

Create/save the supervisor.

Required walkthrough item:

```text
✓ creating a supervisor config
```

---

# 4. Show Workflow Builder

Open:

```text
Builder
```

Show the default blocks:

```text
Order created
Payment
Shipment creation
In transit / delay monitoring
Delivered
Post-delivery support
```

Explain:

> Each block has its own poll interval and Gemini instruction. The workflow can be reordered or customized. New orders receive a snapshot of the currently active Builder configuration.

Set short demo intervals.

Save the active workflow.

---

# 5. Start an Order Run

Click:

```text
+ Start new run
```

Choose the supervisor.

Use:

```text
ORDER-FINAL-DEMO-001
```

Start the run.

Immediately show the order moving through:

```text
AI thinking
        ↓
Monitoring / sleeping
```

Explain:

> Thinking is only temporary. The normal steady state is Monitoring/Sleeping, where Temporal is waiting either for an external Signal or its next durable poll timer.

Required walkthrough item:

```text
✓ starting an order run
```

---

# 6. Show Temporal Workflow

Open Temporal UI.

Locate the workflow for the order.

Show:

- workflow ID,
- running status,
- event history.

Explain:

> This is one durable Temporal workflow for this single order.

Return to the product UI.

---

# 7. Demonstrate Hybrid Sleep and Wake

In the external-system simulator, set:

```text
Payment → Failed
```

Do this only once.

Explain:

> This simulates the payment gateway reporting failure. The state changes and an immediate Signal wakes Temporal.

Show the order briefly processing and returning to:

```text
Monitoring / sleeping
```

Now do nothing.

Wait approximately 10 seconds.

Open the execution logs and filter:

```text
External-state polls
```

Show a new timer-driven:

```text
state_poll
```

Explain:

> I did not click Payment Failed again. The Temporal timer woke automatically and independently re-read the same external state.

This is the most important architecture demonstration.

Required walkthrough items:

```text
✓ agent going to sleep
✓ waking up
✓ sending events into workflow
```

---

# 8. Show Tool Execution

Allow the configured repeated-failure threshold to be reached.

Show:

```text
message_payments_team
```

in the execution logs.

Explain:

> Business actions are mocked Temporal Activities and are stored in the timeline.

Required walkthrough item:

```text
✓ tool execution
```

---

# 9. Demonstrate Payment Recovery

Before or after Human Review, change:

```text
Payment → Confirmed
```

Explain:

> Because this is an external event, the workflow wakes immediately rather than waiting for the next timer.

Show transition:

```text
Payment
    ↓
Shipment creation
```

---

# 10. Demonstrate Shipment Polling

Do not create a shipment immediately.

Wait for the Shipment poll interval.

Show:

```text
state_poll
message_fulfillment_team
```

Then set:

```text
Shipment → Created
```

Show the immediate transition to:

```text
In transit / delay monitoring
```

---

# 11. Add a Live Instruction

While the run is active, add:

```text
This is a VIP customer. Prioritize customer communication if the shipment is delayed.
```

Click:

```text
Add instruction
```

Show the instruction in the execution logs.

Explain:

> Live instructions modify the context for this order only. They are persisted and included in future Gemini decisions.

Required walkthrough item:

```text
✓ adding extra instructions to a live run
```

---

# 12. Demonstrate Shipment Delay

Report:

```text
+8 hours
```

Optionally add a new ETA.

Show actions such as:

```text
message_customer
message_logistics_team
```

Show:

```text
total delay = 8 hours
```

Later report another:

```text
+5 hours
```

Show:

```text
cumulative delay = 13 hours
```

Explain:

> The workflow keeps structured key facts, so it does not forget previous delays.

---

# 13. Demonstrate Human Review

Use either:

### Automatic example

Repeated payment failure / refund / severe operational condition.

or:

### Manual example

Click:

```text
Take human control
```

Show order moving into:

```text
Human review
```

Explain:

> Human Review is not a system error. It means the automation intentionally needs a business decision from an operator.

Show suggested actions.

Enter/select an action such as:

```text
Continue monitoring
```

or:

```text
Contact courier manually and continue monitoring.
```

Apply the decision.

Show the workflow returning to:

```text
Monitoring / sleeping
```

Required walkthrough item:

```text
✓ interrupting a run
```

You may also briefly show the:

```text
End this run
```

control as the permanent termination option.

---

# 14. Mark Order Delivered

Set:

```text
Delivery → Delivered
```

Show:

```text
message_customer
message_fulfillment_team
```

and transition to:

```text
Delivered / support
```

Explain:

> After delivery, recurring payment/shipment polling stops. The workflow is now event-driven and waits only for post-delivery support events or its support-window timeout.

---

# 15. Demonstrate Post-Delivery Support

Optional but recommended.

Before the timeout expires, simulate:

```text
customer_message_received
```

Explain:

> The support event wakes the same workflow immediately and restarts the support window.

Alternatively demonstrate:

```text
refund_requested
```

and show the Human Review path.

---

# 16. Allow Workflow to Complete

After all support work is resolved, do nothing until the support window expires.

Show transition:

```text
Delivered / support
        ↓
Completed
```

Explain:

> The workflow completes only when the support window expires with no unresolved Human Review.

---

# 17. Show Final Summary

Open the Completed run.

Show:

- final summary,
- actions taken,
- key learnings,
- recommendations.

Required walkthrough items:

```text
✓ final summary
✓ learnings
✓ feedback / recommendations
```

---

# 18. Show Execution Logs

Scroll to the bottom execution panel.

Mention that logs are displayed newest first.

Filter through:

```text
External-state polls
Events
AI decisions
Tool calls
Human actions
Instructions
System
```

Click a row and show its structured payload.

Explain:

> The execution log makes the agent behavior observable and gives a complete history of what woke the workflow, what it observed, what actions it executed, and what the human changed.

---

# 19. Closing Explanation

Suggested closing:

> The key idea is that the AI is not continuously running. Temporal keeps one durable supervisor alive for each order. Most of the time the workflow sleeps. It wakes immediately when an external event occurs, or independently on its configured timer to verify the latest state. Deterministic workflow logic manages order state, Gemini handles contextual reasoning, typed activities represent business actions, and Human Review handles decisions that should not be fully automated.

---

# 20. Final Requirement Checklist

Before submitting the video, verify the recording contains:

- [ ] Supervisor configuration creation
- [ ] Builder / workflow configuration
- [ ] Starting an order run
- [ ] Incoming event
- [ ] Workflow sleeping
- [ ] Automatic scheduled wake
- [ ] External-state polling
- [ ] Tool execution
- [ ] Live run-specific instruction
- [ ] Human interruption or termination
- [ ] Human decision and resume
- [ ] Delivery
- [ ] Post-delivery support
- [ ] Completed state
- [ ] Final summary
- [ ] Actions taken
- [ ] Learnings
- [ ] Recommendations / feedback
- [ ] Execution logs
- [ ] Temporal UI
