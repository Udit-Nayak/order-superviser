# Order Supervisor

A long-running AI supervisor for order operations built using **FastAPI**, **Temporal Python SDK**, **Gemini**, **Supabase/PostgreSQL**, and **Next.js**.

The system creates one durable Temporal workflow per order and monitors the order from creation through payment, shipment, delivery, post-delivery support, and final completion.

The final monitoring model is **Hybrid Event + Polling**:

- external order changes wake the workflow immediately through Temporal Signals,
- Temporal timers independently wake the workflow when no event arrives,
- the workflow polls the latest external order state,
- routine cases continue automatically,
- exceptional cases can be handed to a human operator.

---

# Setup Instructions

## 1. Prerequisites

Install:

- Python 3.11+
- Node.js / npm
- Temporal CLI
- Supabase/PostgreSQL project
- Gemini API key

---

## 2. Clone the Repository

```powershell
git clone https://github.com/Udit-Nayak/order-superviser.git
cd order-superviser
```

Project structure:

```text
order-superviser/
│
├── README.md
├── ARCHITECTURE.md
├── WALKTHROUGH_CHECKLIST.md
│
├── backend/
└── frontend/
```

---

## 3. Backend Setup

Open a terminal inside:

```text
backend/
```

Create a virtual environment:

```powershell
python -m venv .venv
```

Activate it:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install backend dependencies:

```powershell
pip install -r requirements.txt
```

---

## 4. Backend Environment Variables

Create:

```text
backend/.env
```

Configure the environment variables used by the project:

```env
TEMPORAL_HOST=localhost:7233
TEMPORAL_NAMESPACE=default
TEMPORAL_TASK_QUEUE=order-supervisor-queue

SUPABASE_DB_URL=<your-supabase-postgres-connection-string>

GEMINI_API_KEY=<your-gemini-api-key>
GEMINI_MODEL=<your-working-gemini-model>
```

Do **not** commit the real `.env` file.

Use `backend/.env.example` as the public reference file.

---

## 5. Database Setup

Open the **Supabase SQL Editor** and run the SQL files in this order:

```text
backend/sql/phase2_schema.sql
backend/sql/hybrid_monitoring_migration.sql
```

The final hybrid-monitoring migration adds/updates:

- workflow runtime-state storage,
- hybrid polling support,
- workflow-template support,
- timeline types required by the final workflow,
- post-delivery workflow status support.

---

## 6. Start Temporal

Open a new terminal.

For local development:

```powershell
temporal server start-dev --db-filename "$HOME\temporal-order-supervisor-demo.db"
```

Temporal Web UI:

```text
http://localhost:8233
```

> When the workflow implementation changes significantly during development, use a new `--db-filename` so old workflow histories do not conflict with the new workflow definition.

---

## 7. Start the Temporal Worker

Open another terminal:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m app.worker
```

Expected startup output is similar to:

```text
Temporal hybrid-monitoring worker connected to localhost:7233
```

Keep this terminal running.

---

## 8. Start FastAPI

Open another terminal:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

FastAPI:

```text
http://localhost:8000
```

Swagger documentation:

```text
http://localhost:8000/docs
```

Health check:

```text
http://localhost:8000/health
```

Expected response:

```json
{
  "status": "ok"
}
```

---

## 9. Frontend Setup

Open another terminal:

```powershell
cd frontend
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

## 10. Services Required During the Demo

Keep these four processes running:

```text
Terminal 1 → Temporal Server
Terminal 2 → Temporal Worker
Terminal 3 → FastAPI
Terminal 4 → Next.js
```

Useful URLs:

```text
Frontend      http://localhost:3000
FastAPI       http://localhost:8000
Swagger       http://localhost:8000/docs
Temporal UI   http://localhost:8233
```

---

# Demo Walkthrough

## 11. Recommended Demo Configuration

For a fast walkthrough, configure small intervals in the Builder:

```text
Payment:              10 seconds
Shipment:             10 seconds
In Transit:           10 seconds
Post-delivery Support: 30 seconds
```

In a production deployment, these values would normally be much longer.

Use a fresh order ID for every clean demo, for example:

```text
ORDER-FINAL-DEMO-001
```

---

## 12. Create a Supervisor

Open the **Setup** tab.

Create a reusable supervisor configuration containing:

- supervisor name,
- base instruction,
- enabled business actions,
- Gemini model configuration.

The five business actions are:

```text
message_fulfillment_team
message_payments_team
message_logistics_team
message_customer
create_internal_note
```

These are implemented as mocked Temporal Activities and are recorded in the execution timeline.

---

## 13. Configure the Workflow Builder

Open the **Builder** tab.

The default workflow is:

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

Save the workflow.

Every new order receives a snapshot of the currently active Builder workflow.

Changing the Builder later does not modify workflows that are already running.

---

## 14. Start an Order Run

Click:

```text
+ Start new run
```

Choose the supervisor and enter:

```text
ORDER-FINAL-DEMO-001
```

The workflow starts with:

```text
Order created
      ↓
Payment monitoring
```

The order should normally settle into:

```text
Monitoring / sleeping
```

The **AI thinking** column should only be short-lived while Gemini or workflow activities are actively processing.

---

## 15. Demonstrate Hybrid Event + Polling

The project uses a **Hybrid Event + Polling** monitoring model.

### Immediate Event Wake

If an external system changes state:

```text
External state changes
      ↓
FastAPI updates canonical state
      ↓
Temporal Signal
      ↓
Workflow wakes immediately
```

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

### Scheduled Polling Wake

If no external event arrives:

```text
Temporal timer expires
      ↓
Workflow wakes automatically
      ↓
get_order_state_activity()
      ↓
Latest external state is read
      ↓
Workflow evaluates it
```

This prevents the workflow from waiting forever if an external webhook is delayed or missed.

---

## 16. Demo External Order State

For the POC, the right-side dashboard simulates external systems such as:

- commerce/order service,
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

In production, this simulated state can be replaced by real external APIs without changing the overall Temporal orchestration model.

---

## 17. Payment Monitoring Demo

Example Builder configuration:

```text
Poll every: 10 seconds
Notify payments after: 2 failed checks
Human review after: 3 failed checks
```

Set:

```text
Payment → Failed
```

only once.

The flow becomes:

```text
Payment failed
      ↓
Immediate Temporal wake
      ↓
Failed check #1
      ↓
Monitoring / sleeping
      ↓
Timer wakes automatically
      ↓
Poll latest state
      ↓
Still failed
      ↓
Failed check #2
      ↓
message_payments_team
      ↓
Sleep again
      ↓
Third failed check
      ↓
message_payments_team
create_internal_note
      ↓
Human Review
```

The important point is that the user does **not** need to click `Payment Failed` repeatedly.

The state remains failed in the external source of truth, and future Temporal timer wakes poll that same state automatically.

If payment becomes confirmed at any point:

```text
Payment → Confirmed
```

the immediate Signal wakes the workflow and it advances to Shipment.

---

## 18. Shipment Monitoring Demo

After payment succeeds:

```text
Payment
   ↓
Shipment creation
```

If shipment is created before the timer expires:

```text
shipment_created
      ↓
Immediate Signal
      ↓
Move to In Transit
```

If shipment is still not created when the scheduled poll fires:

```text
Timer wake
      ↓
Poll latest state
      ↓
shipment = not_created
      ↓
message_fulfillment_team
      ↓
Continue monitoring
```

---

## 19. Shipment Delay Demo

Report a new shipment delay:

```text
+8 hours
```

The workflow stores:

```text
total delay = 8 hours
```

and can execute:

```text
message_customer
message_logistics_team
```

Later report:

```text
+5 hours
```

The workflow stores:

```text
total delay = 13 hours
```

This demonstrates structured memory across multiple events.

---

## 20. Add an Instruction to a Live Run

While the workflow is active, add a run-specific instruction such as:

```text
This is a VIP customer. Prioritize customer communication if the shipment is delayed.
```

The instruction is persisted and becomes part of future Gemini context for this order only.

---

## 21. Human Review / Human-in-the-Loop

Human Review is used when automation reaches a point where a business decision should be made by an operator.

Typical examples:

- repeated payment failures,
- severe shipment delays,
- refund requests,
- manually interrupted orders,
- situations requiring business judgment.

While Human Review is active:

- scheduled polling pauses,
- the Temporal workflow remains durable,
- the operator can choose a suggested action,
- the operator can provide custom instructions,
- important resolving external events can still wake the workflow.

Examples of human actions:

```text
Retry payment now
Ask customer to use another payment method
Contact courier manually
Approve refund review
Continue monitoring
Cancel order
```

The user can also manually interrupt a normally running workflow using:

```text
Take human control
```

After the operator submits a decision, the same Temporal workflow resumes.

Permanent termination is available through:

```text
End this run
```

---

## 22. Delivery and Post-Delivery Support

When the order is delivered:

```text
Delivered
      ↓
message_customer
message_fulfillment_team
      ↓
Delivered / support
```

After confirmed delivery, recurring payment/shipment polling stops.

The workflow now waits only for:

```text
customer_message_received
refund_requested
support-window timeout
```

If a customer message or refund request arrives, the same workflow wakes immediately.

Each handled post-delivery support event restarts the support window.

Example:

```text
Delivered
      ↓
30-second support window
      ↓
Customer message arrives after 20 seconds
      ↓
Handle message
      ↓
Support window restarts
      ↓
30 seconds with no unresolved issue
      ↓
Finalize workflow
```

If a refund enters Human Review, completion waits until the human decision has been resolved.

---

## 23. Final Completion

The workflow moves to **Completed** when:

- the order has reached Post-delivery Support,
- the support window expires,
- there is no unresolved Human Review.

Finalization generates:

- final summary,
- actions taken,
- key learnings,
- recommendations.

The complete timeline remains available in the UI.

---

## 24. Dashboard States

The Kanban contains five columns:

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

- an incoming Signal, or
- the next scheduled poll.

### AI thinking

Short-lived processing state while Gemini or workflow activities execute.

### Human review

Automation intentionally waits for an operator decision.

### Delivered / support

Order is delivered and waiting only for post-delivery support activity or support timeout.

### Completed

Workflow processing is finished.

---

## 25. Execution Logs

The execution panel displays the newest records first.

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

This makes it possible to inspect:

- why the workflow woke,
- what external state it observed,
- what Gemini decided,
- which business actions executed,
- what instructions were added,
- what decisions a human operator made.

---

# Technical Overview

## 26. Tech Stack

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

## 27. One Temporal Workflow Per Order

Each order receives its own long-running Temporal workflow.

Example:

```text
ORDER-1001
→ order-supervisor-<run-id>
```

Temporal persists:

- workflow state,
- timers,
- Signals,
- execution history.

This allows the workflow to survive worker/API restarts while continuing the same order lifecycle.

---

## 28. Production Extension

The POC uses:

```text
order_runtime_states
```

as the simulated external source of truth.

In production it can be replaced by integrations with:

```text
Commerce platform
Payment gateway
Warehouse service
Courier/logistics service
Refund/support service
```

The overall monitoring architecture remains:

```text
External Signal for immediate reaction
+
Scheduled polling for reliability
+
Gemini for contextual reasoning
+
Human Review for business judgment
```

---

## 29. Project Structure

```text
order-superviser/
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
│   ├── .env.example
│   └── requirements.txt
│
└── frontend/
    ├── src/
    │   ├── app/
    │   ├── components/
    │   ├── hooks/
    │   └── lib/
    │
    ├── package.json
    ├── package-lock.json
    └── tsconfig.json
```
