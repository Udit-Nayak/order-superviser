# Order Supervisor

A long-running AI supervisor for order operations, built using **FastAPI**, **Temporal Python SDK**, **Gemini**, **Supabase/PostgreSQL**, and **Next.js**.

The system creates one durable Temporal workflow per order and monitors the order from creation through payment, shipment, delivery, post-delivery support, and final completion.

The final monitoring model is **Hybrid Event + Polling**:

- external order changes wake the workflow immediately through Temporal Signals,
- Temporal timers independently wake the workflow when no event arrives,
- the workflow polls the latest external order state,
- routine cases continue automatically,
- exceptional cases can be handed to a human operator.

---

## 1. Tech Stack

### Backend

- Python 3.11+
- FastAPI
- Temporal Python SDK
- SQLAlchemy async
- asyncpg
- Supabase PostgreSQL
- Google Gemini API

### Frontend

- Next.js App Router
- TypeScript
- Tailwind CSS
- React Query

### Workflow / Infrastructure

- Temporal Server
- Temporal Worker
- PostgreSQL / Supabase
- Gemini API

---

## 2. High-Level Product Flow

```text
Order created
     ↓
Payment monitoring
     ↓
Shipment creation
     ↓
In-transit / delay monitoring
     ↓
Delivered
     ↓
Post-delivery support
     ↓
Completed
```

Before delivery, monitoring uses:

```text
External event
      ↓
Immediate Temporal Signal
      ↓
Workflow wakes

OR

No external event
      ↓
Temporal timer expires
      ↓
Workflow polls latest external state
      ↓
Workflow evaluates current order state
```

After delivery, recurring polling stops.

The workflow moves to **Post-delivery Support**, where it waits only for:

- customer messages,
- refund requests,
- the configured support-window timeout.

When the support window expires without unresolved human intervention, the workflow creates its final summary and moves to **Completed**.

---

## 3. Core Concepts

### One Temporal Workflow Per Order

Each order receives its own long-running Temporal workflow.

Example:

```text
ORDER-1001
→ order-supervisor-<run-id>
```

The workflow survives timers, external events, API restarts, and worker restarts because Temporal persists workflow state and execution history.

---

### Supervisor Configuration

Before starting an order, a user creates a reusable supervisor configuration containing:

- supervisor name,
- base instruction,
- enabled business actions,
- Gemini model configuration.

The required business actions are:

```text
message_fulfillment_team
message_payments_team
message_logistics_team
message_customer
create_internal_note
```

These are mocked Temporal Activities in the POC and are stored in the execution timeline.

---

### Workflow Builder

Each supervisor has an active workflow template.

The default lifecycle is:

```text
1. Order created
2. Payment
3. Shipment creation
4. In transit / delay monitoring
5. Delivered
6. Post-delivery support
```

Each block can be:

- reordered,
- removed,
- inserted,
- configured with its own poll/check interval,
- given a block-specific Gemini instruction.

New orders receive a snapshot of the currently active workflow.

Changing the Builder later does not modify workflows that are already running.

---

## 4. Hybrid Event + Polling Monitoring

The project uses a hybrid monitoring model.

### Immediate Event Wake

If an external system changes state, FastAPI updates the external order state and signals Temporal immediately.

Examples:

```text
payment_confirmed
payment_failed
shipment_created
shipment_delayed
delivered
customer_message_received
refund_requested
```

The workflow does not wait for the timer if an event arrives early.

---

### Scheduled Polling Wake

If no event arrives, Temporal wakes the workflow after the current Builder block's configured poll interval.

The workflow then executes:

```text
get_order_state_activity()
```

and reads the latest external order state.

This prevents the workflow from waiting forever if an external event/webhook is delayed or missed.

---

## 5. Demo External Order State

For the POC, the right-side dashboard acts as a simulator for external systems such as:

- Amazon / order service,
- payment gateway,
- warehouse,
- courier,
- refund service.

The canonical demo order state is stored in:

```text
order_runtime_states
```

Example fields:

```text
payment_status
shipment_status
delivery_status
total_delay_hours
latest_eta
refund_status
customer_message
```

In production, this table can be replaced by real external APIs without changing the Temporal orchestration model.

---

## 6. Payment Monitoring

The Payment block repeatedly checks the canonical payment status.

Example configuration:

```text
Poll every: 10 seconds
Notify payments after: 2 failed checks
Human review after: 3 failed checks
```

Flow:

```text
Payment failed
      ↓
workflow wakes immediately
      ↓
failed check #1
      ↓
sleep / monitoring
      ↓
timer wakes automatically
      ↓
poll latest state
      ↓
still failed
      ↓
failed check #2
      ↓
message_payments_team
      ↓
sleep again
      ↓
third failed check
      ↓
message_payments_team
create_internal_note
      ↓
Human Review
```

If payment becomes confirmed at any time, the workflow wakes immediately and advances to Shipment.

---

## 7. Shipment Monitoring

After payment succeeds, the workflow enters Shipment Creation.

If shipment is created before the timer expires:

```text
shipment_created
      ↓
immediate signal
      ↓
move to In Transit
```

If shipment is still not created when the poll timer fires:

```text
timer wake
      ↓
poll latest state
      ↓
shipment = not_created
      ↓
message_fulfillment_team
      ↓
continue monitoring
```

---

## 8. Shipment Delay Monitoring

When the courier reports a new delay, the workflow stores the cumulative delay.

Example:

```text
first delay: +8 hours
total delay: 8 hours

second delay: +5 hours
total delay: 13 hours
```

The workflow can execute:

```text
message_customer
message_logistics_team
```

and may enter Human Review depending on the current policy.

---

## 9. Human Review / Human-in-the-Loop

Human Review is used when automation reaches a point where a business decision should be made by an operator.

Typical cases include:

- repeated payment failures,
- unusual or severe shipment delays,
- refund requests,
- manually interrupted orders,
- situations requiring business judgment.

While Human Review is active:

- scheduled polling is paused,
- the workflow remains durable,
- an operator can choose a suggested action or enter custom instructions,
- important resolving external events can still wake the workflow.

The operator then chooses:

```text
Apply decision / continue
```

and the same Temporal workflow resumes.

Examples of human actions:

```text
Retry payment now
Ask the customer to use another payment method
Contact the courier manually
Approve refund review
Continue monitoring
Cancel order
```

The dashboard also supports manual interruption through:

```text
Take human control
```

and permanent termination through:

```text
End this run
```

---

## 10. Post-Delivery Support

After delivery:

```text
Delivered
      ↓
message_customer
message_fulfillment_team
      ↓
Post-delivery support
```

At this point, **continuous polling stops**.

The workflow waits only for:

```text
customer_message_received
refund_requested
support-window timeout
```

If a support event arrives, the workflow handles it and restarts the support window.

Example:

```text
Delivered
      ↓
30-second support window
      ↓
customer message arrives at 20 seconds
      ↓
handle message
      ↓
support window restarts
      ↓
30 seconds of no unresolved activity
      ↓
finalize
```

If a refund requires human review, completion waits until the human decision is resolved.

---

## 11. Final Completion

The workflow moves to **Completed** when:

- the lifecycle reaches the Post-delivery Support stage,
- the support window expires,
- there is no unresolved Human Review.

Finalization generates:

- final summary,
- actions taken,
- key learnings,
- recommendations.

The final timeline remains available in the UI.

---

## 12. Dashboard

The dashboard contains five Kanban columns:

```text
Monitoring / sleeping
AI thinking
Human review
Delivered / support
Completed
```

### Monitoring / sleeping

Normal steady state.

The workflow is waiting for:

- an external signal, or
- the next scheduled poll.

### AI thinking

Short-lived state while Gemini or workflow activities are processing.

### Human review

The automation intentionally waits for an operator decision.

### Delivered / support

The order is delivered and waiting only for post-delivery support events or the support timeout.

### Completed

Workflow processing has finished.

---

## 13. Execution Logs

The bottom execution panel shows the newest records first.

Log types include:

```text
state_poll
workflow_block
event
agent_decision
tool_call
human_action
instruction
system
```

Each record contains:

- timestamp,
- type,
- summary,
- structured payload.

This makes it easy to demonstrate exactly how the workflow woke, what it observed, what Gemini decided, and which tools were executed.

---

# Setup Instructions

## 14. Prerequisites

Install:

- Python 3.11+
- Node.js / npm
- Temporal CLI
- Supabase/PostgreSQL project
- Gemini API key

---

## 15. Backend Setup

Open a terminal inside:

```text
backend/
```

Create a virtual environment if it does not already exist:

```powershell
python -m venv .venv
```

Activate it:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install requirements:

```powershell
pip install -r requirements.txt
```

---

## 16. Environment Variables

Create:

```text
backend/.env
```

Configure the existing environment variables used by the project, including:

```env
TEMPORAL_HOST=localhost:7233
TEMPORAL_NAMESPACE=default
TEMPORAL_TASK_QUEUE=order-supervisor-queue

SUPABASE_DB_URL=<your-supabase-postgres-connection-string>

GEMINI_API_KEY=<your-gemini-api-key>
GEMINI_MODEL=<your-working-gemini-model>
```


---

## 17. Database Setup

Run the SQL files in Supabase SQL Editor.

The current hybrid-monitoring schema includes:

```text
backend/sql/phase2_schema.sql
backend/sql/hybrid_monitoring_migration.sql
```

`hybrid_monitoring_migration.sql` adds/updates the runtime state and timeline support needed by the final workflow.

---

## 18. Start Temporal

For development, use a fresh local Temporal database when workflow code has changed significantly.

Example:

```powershell
temporal server start-dev --db-filename "$HOME\temporal-order-supervisor-demo.db"
```

Temporal Web UI:

```text
http://localhost:8233
```

---

## 19. Start Temporal Worker

Open another terminal:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m app.worker
```

Expected startup message is similar to:

```text
Temporal hybrid-monitoring worker connected to localhost:7233
```

---

## 20. Start FastAPI

Open another backend terminal:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

Swagger documentation:

```text
http://localhost:8000/docs
```

Health check:

```text
http://localhost:8000/health
```

---

## 21. Frontend Setup

Open:

```text
frontend/
```

Install dependencies:

```powershell
npm install
```

Create or verify:

```text
frontend/.env.local
```

with:

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

Start Next.js:

```powershell
npm run dev
```

Open:

```text
http://localhost:3000
```

---

## 22. Recommended Demo Configuration

For a fast walkthrough, use small poll intervals such as:

```text
Payment: 10 seconds
Shipment: 10 seconds
In Transit: 10 seconds
Post-delivery Support: 30 seconds
```

For a real production deployment, these values would be longer.

---

## 23. Demo Walkthrough

A strong demonstration sequence is:

```text
1. Create supervisor
2. Open Builder
3. Configure short demo intervals
4. Save workflow
5. Start a fresh order
6. Show Monitoring / Sleeping
7. Set payment to Failed once
8. Wait without touching anything
9. Show Temporal automatically polling the failed state
10. Show payments-team tool execution
11. Change payment to Confirmed
12. Show immediate wake and transition to Shipment
13. Show shipment polling
14. Mark shipment Created
15. Report a delay
16. Show customer/logistics actions
17. Add a live instruction
18. Demonstrate Human Review
19. Apply human decision and resume
20. Mark Delivered
21. Show Delivered / Support
22. Send a customer/refund support event
23. Allow support window to expire
24. Show Completed
25. Show final summary, learnings, recommendations
26. Show execution logs and Temporal UI
```

---

## 24. Project Structure

```text
order-supervisor-phase1/
│
├── README.md
├── ARCHITECTURE.md
├── WALKTHROUGH_CHECKLIST.md
│
├── backend/
│   ├── app/
│   │   ├── activities/
│   │   ├── tools/
│   │   ├── workflows/
│   │   ├── main.py
│   │   ├── worker.py
│   │   ├── models.py
│   │   ├── schemas.py
│   │   └── workflow_defaults.py
│   │
│   ├── scripts/
│   ├── sql/
│   ├── .env
│   └── requirements.txt
│
└── frontend/
    ├── src/
    │   ├── app/
    │   ├── components/
    │   ├── hooks/
    │   └── lib/
    │
    ├── .env.local
    ├── package.json
    └── package-lock.json
```

---

## 25. Production Extension

The POC uses `order_runtime_states` as a simulated external order source.

In production it can be replaced by integrations with systems such as:

```text
Commerce platform
Payment gateway
Warehouse service
Courier/logistics service
Refund/support service
```

The Temporal workflow model remains the same:

```text
external signal for immediate reaction
+
scheduled polling for reliability
+
Gemini for contextual reasoning
+
human review for business judgment
```
