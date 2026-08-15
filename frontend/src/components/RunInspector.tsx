"use client";

import { useMemo, useState, type ReactNode } from "react";

import ErrorState from "@/components/ErrorState";
import {
  useExternalOrderState,
  useFinalSummary,
  useRunActions,
  useRunDetail,
} from "@/hooks/useOrderSupervisor";
import { ApiError } from "@/lib/api";
import type {
  ExternalOrderStatePatch,
  TimelineEntry,
} from "@/lib/types";

const TERMINAL = new Set(["completed", "terminated", "failed"]);

function statusLabel(status: string) {
  if (status === "sleeping") return "Monitoring";
  if (status === "thinking") return "AI thinking";
  if (status === "waiting_review") return "Waiting review";
  if (status === "post_delivery") return "Delivered / support";
  return status.replaceAll("_", " ");
}

export default function RunInspector({ runId }: { runId: string | null }) {
  const run = useRunDetail(runId);
  const externalState = useExternalOrderState(runId);
  const actions = useRunActions(runId);

  const [inlineInstruction, setInlineInstruction] = useState("");
  const [standaloneInstruction, setStandaloneInstruction] = useState("");
  const [humanAction, setHumanAction] = useState("");
  const [selectedBlockId, setSelectedBlockId] = useState("");
  const [delayHours, setDelayHours] = useState("8");
  const [latestEta, setLatestEta] = useState("");
  const [customerMessage, setCustomerMessage] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const terminal = Boolean(run.data && TERMINAL.has(run.data.status));
  const finalSummary = useFinalSummary(runId, terminal);

  const blockChoices = useMemo(() => {
    if (!run.data) return [];

    const previous = run.data.block_history ?? [];
    const current = run.data.current_block
      ? [run.data.current_block]
      : [];

    const allBlocks = [...previous, ...current];

    return allBlocks.filter(
      (block, index, array) =>
        array.findIndex((item) => item.id === block.id) === index,
    );
  }, [run.data]);

  const effectiveBlockId =
    selectedBlockId ||
    run.data?.current_block?.id ||
    blockChoices.at(-1)?.id ||
    "";

  const blockLogs = useMemo(() => {
    if (!run.data || !effectiveBlockId) return [];

    return run.data.timeline.filter(
      (entry) =>
        String(entry.payload?.block_id ?? "") === effectiveBlockId,
    );
  }, [effectiveBlockId, run.data]);

  const isPending =
    actions.updateExternalState.isPending ||
    actions.addInstruction.isPending ||
    actions.humanAction.isPending ||
    actions.interrupt.isPending ||
    actions.terminate.isPending;

  const execute = async (
    fn: () => Promise<unknown>,
    success: string,
  ) => {
    setError("");
    setMessage("");

    try {
      await fn();
      setMessage(success);
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 409) {
        setError(caught.detail);
      } else {
        setError(
          caught instanceof Error ? caught.message : "Action failed.",
        );
      }
    }
  };

  const changeExternalState = async (
    patch: ExternalOrderStatePatch,
    success: string,
  ) => {
    const instruction = inlineInstruction.trim();

    await execute(async () => {
      await actions.updateExternalState.mutateAsync({
        ...patch,
        ...(instruction ? { instruction } : {}),
      });
      if (instruction) setInlineInstruction("");
    }, success);
  };

  if (!runId) {
    return (
      <aside className="flex h-screen items-center justify-center border-l border-slate-200 bg-white p-6 text-center text-sm text-slate-500">
        Select an order to inspect and control it.
      </aside>
    );
  }

  if (run.isLoading) {
    return (
      <aside className="h-screen border-l border-slate-200 bg-white p-5 text-sm text-slate-500">
        Loading order...
      </aside>
    );
  }

  if (run.error || !run.data) {
    return (
      <aside className="h-screen border-l border-slate-200 bg-white p-5">
        <ErrorState
          message={run.error?.message ?? "Run unavailable"}
          onRetry={() => void run.refetch()}
        />
      </aside>
    );
  }

  const detail = run.data;
  const state = externalState.data ?? detail.external_state;
  const suggestions = suggestedHumanActions(
    detail.current_block?.block_type,
  );

  return (
    <aside className="flex h-screen flex-col border-l border-slate-200 bg-white">
      <header className="border-b border-slate-200 p-5">
        <p className="text-xs font-bold uppercase tracking-wider text-slate-500">
          Selected order
        </p>

        <div className="mt-1 flex items-start justify-between gap-3">
          <h2 className="text-xl font-bold">{detail.order_id}</h2>
          <span className="rounded-full bg-slate-950 px-3 py-1 text-xs font-semibold capitalize text-white">
            {statusLabel(detail.status)}
          </span>
        </div>

        <div className="mt-4">
          <p className="text-xs text-slate-400">Next scheduled poll</p>
          <p className="mt-1 text-sm font-medium">
            {detail.next_wake_at
              ? new Date(detail.next_wake_at).toLocaleString()
              : detail.status === "waiting_review"
                ? "Paused for human decision"
                : terminal
                  ? "Monitoring finished"
                  : "No timer currently scheduled"}
          </p>
        </div>
      </header>

      <div className="flex-1 space-y-5 overflow-y-auto p-5">
        <section>
          <div className="flex items-end justify-between gap-2">
            <div>
              <p className="text-xs font-bold uppercase tracking-wider text-slate-500">
                Workflow progress
              </p>
              <h3 className="mt-1 text-lg font-bold">
                {detail.current_block?.label ?? "Workflow finished"}
              </h3>
            </div>

            {blockChoices.length ? (
              <select
                value={effectiveBlockId}
                onChange={(event) =>
                  setSelectedBlockId(event.target.value)
                }
                className="max-w-[180px] rounded-lg border border-slate-300 px-2 py-2 text-xs"
              >
                {blockChoices.map((block, index) => (
                  <option
                    key={`${block.id}-${block.label}-${index}`}
                    value={block.id}
                  >
                    {block.label}
                  </option>
                ))}
              </select>
            ) : null}
          </div>

          {detail.current_block?.instruction ? (
            <p className="mt-2 rounded-lg bg-slate-50 p-3 text-sm leading-5 text-slate-600">
              {detail.current_block.instruction}
            </p>
          ) : null}

          <div className="mt-3 max-h-48 overflow-y-auto rounded-xl border border-slate-200">
            {blockLogs.length ? (
              blockLogs.map((entry, index) => (
                <BlockLog
                  key={`${entry.created_at}-${index}`}
                  entry={entry}
                />
              ))
            ) : (
              <p className="p-3 text-sm text-slate-400">
                No logs recorded for this block yet.
              </p>
            )}
          </div>

          <details className="mt-3 rounded-xl border border-slate-200 bg-slate-50">
            <summary className="cursor-pointer px-3 py-2 text-xs font-semibold text-slate-600">
              AI compact memory
            </summary>
            <p className="border-t border-slate-200 px-3 py-3 text-sm leading-5 text-slate-700">
              {detail.memory_summary ||
                "No compact memory has been generated yet."}
            </p>
          </details>
        </section>

        <section className="rounded-xl border border-blue-200 bg-blue-50 p-4">
          <div className="flex items-start justify-between gap-2">
            <div>
              <p className="text-xs font-bold uppercase tracking-wider text-blue-700">
                Demo external systems
              </p>
              <h3 className="mt-1 text-sm font-bold text-blue-950">
                Canonical order state
              </h3>
            </div>
            <span className="rounded-full bg-white px-2 py-1 text-[10px] font-bold uppercase text-blue-700">
              Event + polling source
            </span>
          </div>

          <p className="mt-2 text-xs leading-5 text-blue-900">
            These controls simulate Amazon/payment/warehouse/courier updates.
            A change sends an immediate Temporal signal. Later timer wakes poll
            this same state automatically, so you do not have to repeat the
            same event manually.
          </p>

          {externalState.error ? (
            <div className="mt-3">
              <ErrorState
                title="External state unavailable"
                message={externalState.error.message}
                onRetry={() => void externalState.refetch()}
              />
            </div>
          ) : (
            <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
              <StateValue
                label="Payment"
                value={state?.payment_status ?? "—"}
              />
              <StateValue
                label="Shipment"
                value={state?.shipment_status ?? "—"}
              />
              <StateValue
                label="Delivery"
                value={state?.delivery_status ?? "—"}
              />
              <StateValue
                label="Total delay"
                value={`${Number(state?.total_delay_hours ?? 0)} h`}
              />
              <StateValue
                label="Latest ETA"
                value={
                  state?.latest_eta
                    ? new Date(state.latest_eta).toLocaleString()
                    : "—"
                }
                wide
              />
            </div>
          )}

          {!terminal ? (
            <div className="mt-4 space-y-4">
              <label className="block">
                <span className="text-xs font-semibold text-blue-950">
                  Optional instruction with next external change
                </span>
                <textarea
                  value={inlineInstruction}
                  onChange={(event) =>
                    setInlineInstruction(event.target.value)
                  }
                  rows={2}
                  placeholder="Example: This is a VIP order; prioritize customer communication."
                  className="mt-1 w-full rounded-lg border border-blue-200 bg-white p-2 text-sm text-slate-900"
                />
              </label>

              <SimulatorGroup title="Payment gateway">
                <SimulatorButton
                  disabled={isPending}
                  onClick={() =>
                    void changeExternalState(
                      { payment_status: "pending" },
                      "Payment gateway state changed to pending.",
                    )
                  }
                >
                  Pending
                </SimulatorButton>
                <SimulatorButton
                  disabled={isPending}
                  onClick={() =>
                    void changeExternalState(
                      { payment_status: "failed" },
                      "Payment gateway reported FAILED. Temporal woke immediately; later polls will re-check it automatically.",
                    )
                  }
                >
                  Failed
                </SimulatorButton>
                <SimulatorButton
                  disabled={isPending}
                  onClick={() =>
                    void changeExternalState(
                      { payment_status: "confirmed" },
                      "Payment gateway reported CONFIRMED.",
                    )
                  }
                >
                  Confirmed
                </SimulatorButton>
              </SimulatorGroup>

              <SimulatorGroup title="Warehouse / shipment">
                <SimulatorButton
                  disabled={isPending}
                  onClick={() =>
                    void changeExternalState(
                      { shipment_status: "not_created" },
                      "Shipment state is now not created.",
                    )
                  }
                >
                  Not created
                </SimulatorButton>
                <SimulatorButton
                  disabled={isPending}
                  onClick={() =>
                    void changeExternalState(
                      { shipment_status: "created" },
                      "Warehouse reported shipment created.",
                    )
                  }
                >
                  Created
                </SimulatorButton>
                <SimulatorButton
                  disabled={isPending}
                  onClick={() =>
                    void changeExternalState(
                      { shipment_status: "in_transit" },
                      "Courier reported shipment in transit.",
                    )
                  }
                >
                  In transit
                </SimulatorButton>
              </SimulatorGroup>

              <div className="rounded-lg border border-blue-200 bg-white p-3">
                <p className="text-xs font-bold uppercase tracking-wide text-slate-500">
                  Report new shipment delay
                </p>
                <div className="mt-2 grid grid-cols-[100px_1fr] gap-2">
                  <label className="text-xs text-slate-600">
                    + Hours
                    <input
                      type="number"
                      min={0}
                      step="0.5"
                      value={delayHours}
                      onChange={(event) =>
                        setDelayHours(event.target.value)
                      }
                      className="mt-1 w-full rounded-lg border border-slate-300 px-2 py-2 text-sm"
                    />
                  </label>
                  <label className="text-xs text-slate-600">
                    Updated ETA
                    <input
                      type="datetime-local"
                      value={latestEta}
                      onChange={(event) =>
                        setLatestEta(event.target.value)
                      }
                      className="mt-1 w-full rounded-lg border border-slate-300 px-2 py-2 text-sm"
                    />
                  </label>
                </div>
                <button
                  type="button"
                  disabled={
                    isPending ||
                    Number(delayHours) <= 0
                  }
                  onClick={() =>
                    void changeExternalState(
                      {
                        additional_delay_hours: Number(delayHours),
                        ...(latestEta
                          ? {
                              latest_eta: new Date(
                                latestEta,
                              ).toISOString(),
                            }
                          : {}),
                      },
                      `Courier added ${delayHours} hour(s) of delay.`,
                    )
                  }
                  className="mt-2 w-full rounded-lg bg-blue-950 px-3 py-2 text-sm font-semibold text-white disabled:opacity-40"
                >
                  Report delay
                </button>
              </div>

              <SimulatorGroup title="Delivery">
                <SimulatorButton
                  disabled={isPending}
                  onClick={() =>
                    void changeExternalState(
                      {
                        shipment_status: "delivered",
                        delivery_status: "delivered",
                      },
                      "Courier reported DELIVERED.",
                    )
                  }
                >
                  Mark delivered
                </SimulatorButton>
              </SimulatorGroup>

              <div className="rounded-lg border border-blue-200 bg-white p-3">
                <p className="text-xs font-bold uppercase tracking-wide text-slate-500">
                  Post-delivery input
                </p>
                <textarea
                  value={customerMessage}
                  onChange={(event) =>
                    setCustomerMessage(event.target.value)
                  }
                  rows={2}
                  placeholder="Simulate a customer message..."
                  className="mt-2 w-full rounded-lg border border-slate-300 p-2 text-sm"
                />
                <div className="mt-2 grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    disabled={isPending || !customerMessage.trim()}
                    onClick={() =>
                      void changeExternalState(
                        {
                          customer_message:
                            customerMessage.trim(),
                        },
                        "Customer message received.",
                      ).then(() => setCustomerMessage(""))
                    }
                    className="rounded-lg border border-slate-300 px-2 py-2 text-xs font-semibold disabled:opacity-40"
                  >
                    Receive message
                  </button>
                  <button
                    type="button"
                    disabled={isPending}
                    onClick={() =>
                      void changeExternalState(
                        { refund_status: "requested" },
                        "Refund service reported a new refund request.",
                      )
                    }
                    className="rounded-lg border border-slate-300 px-2 py-2 text-xs font-semibold disabled:opacity-40"
                  >
                    Request refund
                  </button>
                </div>
              </div>
            </div>
          ) : null}
        </section>

        {error ? (
          <ErrorState title="Action rejected" message={error} />
        ) : null}

        {message ? (
          <p className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm leading-5 text-emerald-900">
            {message}
          </p>
        ) : null}

        {terminal ? (
          <section>
            <h3 className="text-sm font-bold">Final summary</h3>

            {finalSummary.isLoading ? (
              <p className="mt-2 text-sm text-slate-500">
                Loading final summary...
              </p>
            ) : finalSummary.error ? (
              <div className="mt-2">
                <ErrorState
                  title="Final summary unavailable"
                  message={finalSummary.error.message}
                  onRetry={() => void finalSummary.refetch()}
                />
              </div>
            ) : finalSummary.data ? (
              <div className="mt-2 space-y-3 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm">
                <p>{finalSummary.data.summary}</p>
                <SummaryList
                  title="Actions taken"
                  items={finalSummary.data.actions_taken}
                />
                <SummaryList
                  title="Key learnings"
                  items={finalSummary.data.key_learnings}
                />
                <SummaryList
                  title="Recommendations"
                  items={finalSummary.data.recommendations}
                />
              </div>
            ) : null}
          </section>
        ) : (
          <>
            <section className="rounded-xl border border-slate-200 p-3">
              <p className="text-xs font-bold uppercase tracking-wider text-slate-500">
                Standalone inbound instruction
              </p>

              <textarea
                value={standaloneInstruction}
                onChange={(event) =>
                  setStandaloneInstruction(event.target.value)
                }
                rows={3}
                placeholder="Example: Contact the customer if cumulative delay exceeds 12 hours."
                className="mt-2 w-full rounded-lg border border-slate-300 p-2 text-sm"
              />

              <button
                type="button"
                disabled={isPending || !standaloneInstruction.trim()}
                onClick={() =>
                  void execute(async () => {
                    await actions.addInstruction.mutateAsync(
                      standaloneInstruction.trim(),
                    );
                    setStandaloneInstruction("");
                  }, "Instruction saved for this order.")
                }
                className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold disabled:opacity-40"
              >
                Add instruction
              </button>
            </section>

            <section
              className={`rounded-xl border p-4 ${
                detail.human_intervention_required ||
                detail.status === "waiting_review"
                  ? "border-amber-300 bg-amber-50"
                  : "border-slate-200 bg-slate-50"
              }`}
            >
              <h3 className="text-sm font-bold">Handle the case now</h3>

              {detail.human_intervention_required ||
              detail.status === "waiting_review" ? (
                <>
                  <p className="mt-1 text-xs leading-5 text-amber-900">
                    Timer polling is intentionally stopped while a human
                    decision is required. Choose a suggestion or enter custom
                    text. The same Temporal workflow resumes afterward.
                  </p>

                  <div className="mt-3 flex flex-wrap gap-2">
                    {suggestions.map((suggestion) => (
                      <button
                        key={suggestion}
                        type="button"
                        onClick={() => setHumanAction(suggestion)}
                        className="rounded-full border border-amber-300 bg-white px-3 py-1.5 text-xs font-medium"
                      >
                        {suggestion}
                      </button>
                    ))}
                  </div>

                  <textarea
                    value={humanAction}
                    onChange={(event) =>
                      setHumanAction(event.target.value)
                    }
                    rows={4}
                    placeholder="Describe the decision/action..."
                    className="mt-3 w-full rounded-lg border border-amber-300 bg-white p-2 text-sm"
                  />

                  <button
                    type="button"
                    disabled={isPending || !humanAction.trim()}
                    onClick={() =>
                      void execute(async () => {
                        await actions.humanAction.mutateAsync(
                          humanAction.trim(),
                        );
                        setHumanAction("");
                      }, "Human decision accepted. Automated monitoring resumed.")
                    }
                    className="mt-2 w-full rounded-lg bg-amber-950 px-3 py-2 text-sm font-semibold text-white disabled:opacity-40"
                  >
                    Handle case & continue
                  </button>
                </>
              ) : (
                <p className="mt-1 text-sm text-slate-500">
                  No human intervention is currently required.
                </p>
              )}
            </section>

            {detail.status !== "waiting_review" ? (
              <button
                type="button"
                disabled={isPending}
                onClick={() =>
                  void execute(
                    () => actions.interrupt.mutateAsync(),
                    "Automation interrupted. Human control is now requested.",
                  )
                }
                className="w-full rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm font-semibold text-amber-900 disabled:opacity-40"
              >
                Take human control
              </button>
            ) : null}

            <button
              type="button"
              disabled={isPending}
              onClick={() => {
                if (
                  window.confirm(
                    `End monitoring for ${detail.order_id}?`,
                  )
                ) {
                  void execute(
                    () => actions.terminate.mutateAsync(),
                    "Termination requested.",
                  );
                }
              }}
              className="w-full rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-sm font-semibold text-red-800 disabled:opacity-40"
            >
              End this run
            </button>
          </>
        )}
      </div>
    </aside>
  );
}

function SimulatorGroup({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="rounded-lg border border-blue-200 bg-white p-3">
      <p className="text-xs font-bold uppercase tracking-wide text-slate-500">
        {title}
      </p>
      <div className="mt-2 flex flex-wrap gap-2">{children}</div>
    </div>
  );
}

function SimulatorButton({
  children,
  disabled,
  onClick,
}: {
  children: ReactNode;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className="rounded-lg border border-slate-300 px-3 py-2 text-xs font-semibold text-slate-800 hover:bg-slate-50 disabled:opacity-40"
    >
      {children}
    </button>
  );
}

function StateValue({
  label,
  value,
  wide = false,
}: {
  label: string;
  value: string;
  wide?: boolean;
}) {
  return (
    <div
      className={`rounded-lg border border-blue-100 bg-white p-2 ${
        wide ? "col-span-2" : ""
      }`}
    >
      <p className="text-[10px] font-bold uppercase tracking-wide text-slate-400">
        {label}
      </p>
      <p className="mt-1 break-words font-semibold capitalize text-slate-800">
        {value.replaceAll("_", " ")}
      </p>
    </div>
  );
}

function BlockLog({ entry }: { entry: TimelineEntry }) {
  return (
    <article className="border-b border-slate-100 p-3 last:border-0">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[10px] font-bold uppercase tracking-wide text-slate-500">
          {entry.type.replaceAll("_", " ")}
        </span>
        <time className="text-[10px] text-slate-400">
          {new Date(entry.created_at).toLocaleTimeString()}
        </time>
      </div>
      <p className="mt-1 text-xs leading-5 text-slate-700">
        {entry.summary}
      </p>
    </article>
  );
}

function SummaryList({
  title,
  items,
}: {
  title: string;
  items: string[];
}) {
  return (
    <div>
      <p className="font-semibold">{title}</p>
      {items.length ? (
        <ul className="mt-1 list-disc space-y-1 pl-5">
          {items.map((item, index) => (
            <li key={`${title}-${index}`}>{item}</li>
          ))}
        </ul>
      ) : (
        <p className="mt-1 text-slate-500">None recorded.</p>
      )}
    </div>
  );
}

function suggestedHumanActions(blockType?: string) {
  if (blockType === "payment") {
    return [
      "Retry payment now",
      "Ask customer to use another payment method",
      "Cancel order",
    ];
  }

  if (blockType === "shipment") {
    return [
      "Continue monitoring",
      "Contact fulfillment team manually",
      "Escalate to specialist",
    ];
  }

  if (blockType === "in_transit") {
    return [
      "Continue monitoring",
      "Contact courier manually",
      "Escalate to specialist",
    ];
  }

  if (blockType === "post_delivery") {
    return [
      "Continue support monitoring",
      "Approve refund review",
      "Close order",
    ];
  }

  return [
    "Continue monitoring",
    "Escalate to specialist",
    "Close order",
  ];
}
