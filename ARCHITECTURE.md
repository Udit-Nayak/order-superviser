# Architecture Note

## 1. Objective

The Order Supervisor is a long-running AI workflow that monitors one order throughout its lifecycle.

The central design goal is to provide:

- durable execution,
- immediate reaction to external changes,
- independent scheduled checking,
- AI-assisted operational decisions,
- controlled business actions,
- human intervention for exceptional cases,
- persistent execution history.

---

## 2. System Architecture

```text
                         ┌─────────────────────┐
                         │      Next.js UI     │
                         │                     │
                         │ Setup / Builder     │
                         │ Kanban              │
                         │ External Simulator  │
                         │ Human Review        │
                         │ Execution Logs      │
                         └──────────┬──────────┘
                                    │ HTTP
                                    ▼
                         ┌─────────────────────┐
                         │       FastAPI       │
                         │                     │
                         │ Supervisors         │
                         │ Workflow templates  │
                         │ Runs                │
                         │ External state API  │
                         │ Signals / controls  │
                         └───────┬───────┬─────┘
                                 │       │
                                 │       │
                         SQL     │       │ Temporal API
                                 │       │
                                 ▼       ▼
                   ┌────────────────┐  ┌─────────────────┐
                   │ Supabase /     │  │ Temporal Server │
                   │ PostgreSQL     │  │                 │
                   │                │  │ Workflow state  │
                   │ Runs           │  │ Timers          │
                   │ Timeline       │  │ Signals         │
                   │ Memory         │  │ Durability      │
                   │ Runtime state  │  └────────┬────────┘
                   └────────────────┘           │
                                                ▼
                                      ┌───────────────────┐
                                      │ Temporal Worker   │
                                      │                   │
                                      │ OrderSupervisor   │
                                      │ Workflow          │
                                      │ Activities        │
                                      └───────┬───────────┘
                                              │
                           ┌──────────────────┼─────────────────┐
                           │                  │                 │
                           ▼                  ▼                 ▼
                    ┌────────────┐    ┌─────────────┐   ┌──────────────┐
                    │ Gemini AI  │    │ Business     │   │ External     │
                    │ reasoning  │    │ tool actions │   │ state poll   │
                    └────────────┘    └─────────────┘   └──────────────┘
```

---

## 3. Workflow Ownership

There is one Temporal workflow per order.

FastAPI starts the workflow when the order is created.

The workflow owns:

- lifecycle state,
- current workflow block,
- timers,
- pending signals,
- compact memory,
- block history,
- human-intervention state,
- workflow finalization.

Supabase is used as the queryable product store for:

- supervisors,
- workflow templates,
- runs,
- timeline entries,
- memory snapshots,
- instructions,
- final summaries,
- demo external order state.

---

## 4. Workflow Template Snapshot

The Builder defines the active workflow for a supervisor.

When a new order starts, the current workflow template is copied into the Temporal workflow input.

This means:

```text
Builder changed later
        ↓
new orders use new configuration

existing order
        ↓
continues using original workflow snapshot
```

This prevents active workflows from changing unexpectedly during execution.

---

## 5. Hybrid Monitoring Model

The final design uses **event-driven signals plus scheduled polling**.

### Event Path

```text
External system state changes
       ↓
FastAPI updates external state
       ↓
Temporal Signal
       ↓
workflow wakes immediately
       ↓
poll latest canonical state
       ↓
evaluate
```

### Polling Path

```text
No external signal arrives
       ↓
Temporal durable timer expires
       ↓
workflow wakes
       ↓
get_order_state_activity
       ↓
read latest canonical state
       ↓
evaluate
```

This provides both:

- fast response,
- resilience against missed/delayed external events.

---

## 6. Deterministic State vs AI Reasoning

Basic order facts are handled deterministically in workflow code.

Examples:

```text
payment status
shipment status
delivery status
retry/check count
cumulative delay
block transitions
terminal conditions
```

Gemini is used for contextual reasoning such as:

- interpreting live instructions,
- deciding which allowed business actions are appropriate,
- generating operational/customer-facing reasoning,
- interpreting free-text human actions,
- compacting memory,
- generating final summary and recommendations.

This separation avoids giving the LLM ownership of critical lifecycle state transitions.

---

## 7. External Order State

The demo uses the PostgreSQL table:

```text
order_runtime_states
```

as the canonical external state.

The frontend simulator changes this state.

For example:

```text
Payment -> Failed
```

updates the database once and immediately signals Temporal.

Future timer wakes query the same database again.

Therefore a payment failure does not need to be clicked repeatedly for every timer cycle.

In a production implementation, this table can be replaced by real commerce/payment/warehouse/logistics APIs.

---

## 8. Temporal Signals

Signals are used for external and operator-driven changes.

Examples include:

```text
external_state_changed
add_instruction
human_action
interrupt_now
terminate_now
```

Signals allow the same workflow execution to react while sleeping.

---

## 9. Temporal Timers

Pre-delivery workflow blocks contain configurable polling intervals.

Typical flow:

```text
evaluate current state
       ↓
nothing terminal/actionable
       ↓
schedule durable timer
       ↓
Monitoring / Sleeping
       ↓
timer expires
       ↓
poll again
```

Temporal persists the timer and workflow state even if the worker restarts.

---

## 10. Post-Delivery Architecture

After delivery, continuous polling is intentionally stopped.

The workflow enters:

```text
Post-delivery Support
```

and waits only for:

- customer support signals,
- refund signals,
- a one-shot inactivity/support timeout.

Each handled support event restarts the support timeout.

When the timeout expires with no unresolved Human Review:

```text
final summary
      ↓
persist final state
      ↓
Completed
```

---

## 11. Business Actions

The five required actions are implemented as Temporal Activities:

```text
message_fulfillment_team
message_payments_team
message_logistics_team
message_customer
create_internal_note
```

The POC does not contact real external systems.

Instead, each action:

- validates typed arguments,
- executes as a Temporal Activity,
- creates a structured timeline record,
- appears in the execution log UI.

This provides a clear extension point for real integrations later.

---

## 12. Memory

The workflow maintains two levels of context:

### Compact Memory

A rolling Gemini-generated summary of the most important current context.

### Structured Key Facts

Examples:

```text
payment_failures
total_shipment_delay_hours
latest_eta
delivery status
notification markers
```

The compact memory prevents prompt context from growing indefinitely while preserving key order context.

---

## 13. Human-in-the-Loop

Human Review is a deliberate workflow state, not an error state.

It is used when:

- repeated payment failure crosses a threshold,
- a refund requires approval,
- a serious operational condition needs business judgment,
- an operator manually interrupts the workflow.

During Human Review:

- scheduled polling stops,
- workflow execution remains durable,
- the operator enters a decision,
- the decision becomes a live instruction,
- Gemini can interpret the decision,
- the same workflow resumes.

Important resolving external events may still wake the workflow even while Human Review is active.

---

## 14. Failure / Retry Behavior

Temporal Activities use retry policies for transient failures.

Examples:

- Gemini request failure,
- database activity failure,
- temporary activity errors.

Workflow orchestration remains durable.

For AI failures, deterministic safe fallbacks can be used so the workflow does not lose its operational state.

---

## 15. Workflow Completion

The LLM does not have sole authority to finish an order.

Completion is owned by deterministic workflow lifecycle rules.

The main normal completion path is:

```text
Delivered
      ↓
Post-delivery Support
      ↓
support timeout expires
      ↓
no unresolved Human Review
      ↓
final summary generated
      ↓
Completed
```

An operator may also explicitly terminate a run.

---

## 16. UI Architecture

The dashboard provides:

### Setup

Creates supervisor configuration.

### Builder

Defines the active workflow template.

### Kanban

Displays current operational state:

```text
Monitoring / sleeping
AI thinking
Human review
Delivered / support
Completed
```

### Right-Side Inspector

Provides:

- current workflow block,
- historical block logs,
- compact memory,
- external-system simulator,
- live instructions,
- human-review actions,
- interrupt/terminate controls.

### Execution Panel

Displays newest-first logs with filters for:

```text
state polls
workflow blocks
events
AI decisions
tool calls
human actions
instructions
system events
```

---

## 17. Timing

Temporal workflow code uses:

```text
workflow.now()
```

and Temporal timers rather than raw Python wall-clock timing inside deterministic orchestration.

The frontend converts ISO timestamps to the browser's local PC time for display.

---

## 18. Key Design Decision

The final architecture deliberately separates:

```text
External facts
        ↓
deterministic workflow state

AI interpretation
        ↓
Gemini

Business execution
        ↓
typed Temporal Activities

Exceptional judgment
        ↓
Human Review
```

This combination provides a durable, explainable, and demo-friendly AI order supervisor.
