"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import ErrorState from "@/components/ErrorState";
import {
  useActiveWorkflow,
  useSaveWorkflow,
  useStartRun,
  useSupervisors,
} from "@/hooks/useOrderSupervisor";
import { WORKFLOW_BLOCK_TYPES } from "@/lib/constants";
import type {
  WorkflowBlock,
  WorkflowBlockType,
  WorkflowTemplate,
} from "@/lib/types";

type Props = {
  onRunStarted: (runId: string) => void;
};

function newId(type: WorkflowBlockType) {
  return `${type}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
}

function newBlock(type: WorkflowBlockType): WorkflowBlock {
  const label =
    WORKFLOW_BLOCK_TYPES.find((item) => item.value === type)?.label ?? type;

  return {
    id: newId(type),
    block_type: type,
    label,
    wait_seconds:
      type === "order_created" || type === "delivered" ? 0 : 10,
    instruction: "",
    settings:
      type === "payment"
        ? {
            notify_after_failures: 2,
            human_after_failures: 3,
          }
        : type === "shipment"
          ? { notify_fulfillment_when_overdue: true }
          : type === "in_transit"
            ? { human_on_new_delay: true }
            : {},
  };
}

export default function WorkflowBuilder({ onRunStarted }: Props) {
  const supervisors = useSupervisors();
  const [supervisorId, setSupervisorId] = useState("");

  const effectiveSupervisorId =
    supervisorId || supervisors.data?.[0]?.id || "";

  const activeWorkflow = useActiveWorkflow(
    effectiveSupervisorId || null,
  );

  if (supervisors.isLoading) {
    return <p className="p-5 text-sm text-slate-500">Loading supervisors...</p>;
  }

  if (supervisors.error) {
    return (
      <div className="p-5">
        <ErrorState
          message={supervisors.error.message}
          onRetry={() => void supervisors.refetch()}
        />
      </div>
    );
  }

  if (!supervisors.data?.length) {
    return (
      <p className="m-5 rounded-xl bg-amber-50 p-3 text-sm text-amber-900">
        Create a supervisor in Setup first. Its generalized workflow will be
        created automatically.
      </p>
    );
  }

  return (
    <div className="space-y-4 p-4">
      <section className="rounded-xl border border-slate-200 bg-slate-50 p-3">
        <p className="text-xs font-bold uppercase tracking-wider text-slate-500">
          Workflow owner
        </p>

        <label className="mt-2 block text-sm font-medium">
          Supervisor
          <select
            value={effectiveSupervisorId}
            onChange={(event) => setSupervisorId(event.target.value)}
            className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2"
          >
            {supervisors.data.map((supervisor) => (
              <option key={supervisor.id} value={supervisor.id}>
                {supervisor.name}
              </option>
            ))}
          </select>
        </label>

        <div className="mt-3 rounded-lg border border-blue-200 bg-blue-50 p-3 text-xs leading-5 text-blue-950">
          <p className="font-bold">Hybrid monitoring rule</p>
          <p className="mt-1">
            An external state change wakes the order immediately. If nothing
            arrives, the block&apos;s poll interval wakes Temporal and the
            workflow reads the latest external order state itself.
          </p>
        </div>
      </section>

      {activeWorkflow.isLoading ? (
        <p className="rounded-xl border border-slate-200 p-4 text-sm text-slate-500">
          Loading active workflow...
        </p>
      ) : activeWorkflow.error ? (
        <ErrorState
          title="Could not load workflow"
          message={activeWorkflow.error.message}
          onRetry={() => void activeWorkflow.refetch()}
        />
      ) : activeWorkflow.data ? (
        <WorkflowEditor
          key={`${effectiveSupervisorId}:${activeWorkflow.data.id}`}
          supervisorId={effectiveSupervisorId}
          initialTemplate={activeWorkflow.data}
          onRunStarted={onRunStarted}
        />
      ) : null}
    </div>
  );
}

function WorkflowEditor({
  supervisorId,
  initialTemplate,
  onRunStarted,
}: {
  supervisorId: string;
  initialTemplate: WorkflowTemplate;
  onRunStarted: (runId: string) => void;
}) {
  const saveWorkflow = useSaveWorkflow();
  const startRun = useStartRun();
  const queryClient = useQueryClient();

  // The parent keys this component by template ID. A newly fetched template
  // therefore remounts this editor instead of copying query data into state
  // from useEffect.
  const [name, setName] = useState(initialTemplate.name);
  const [blocks, setBlocks] = useState<WorkflowBlock[]>(
    initialTemplate.blocks,
  );
  const [testOrderId, setTestOrderId] = useState("ORDER-DEMO-001");
  const [addType, setAddType] = useState<WorkflowBlockType>("payment");
  const [insertAt, setInsertAt] = useState(1);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const updateBlock = (
    id: string,
    patch: Partial<WorkflowBlock>,
  ) => {
    setBlocks((current) =>
      current.map((block) =>
        block.id === id ? { ...block, ...patch } : block,
      ),
    );
  };

  const updateSetting = (
    id: string,
    key: string,
    value: string | number | boolean,
  ) => {
    setBlocks((current) =>
      current.map((block) =>
        block.id === id
          ? {
              ...block,
              settings: {
                ...block.settings,
                [key]: value,
              },
            }
          : block,
      ),
    );
  };

  const move = (index: number, delta: number) => {
    setBlocks((current) => {
      const target = index + delta;
      if (target < 0 || target >= current.length) return current;

      const next = [...current];
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  };

  const addBlock = () => {
    const position = Math.max(
      1,
      Math.min(insertAt, blocks.length + 1),
    );

    setBlocks((current) => {
      const next = [...current];
      next.splice(position - 1, 0, newBlock(addType));
      return next;
    });
  };

  const save = async () => {
    if (!blocks.length) return null;

    setError("");
    setMessage("");

    try {
      const saved = await saveWorkflow.mutateAsync({
        name: name.trim() || "Default order lifecycle",
        supervisor_id: supervisorId,
        blocks,
        active: true,
      });

      setMessage(
        "Saved as the active workflow. New orders will receive this exact workflow snapshot.",
      );
      return saved;
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not save workflow.",
      );
      return null;
    }
  };

  const run = async () => {
    if (!testOrderId.trim() || !blocks.length) return;

    setError("");
    setMessage("");

    const saved = await save();
    if (!saved) return;

    try {
      const started = await startRun.mutateAsync({
        order_id: testOrderId.trim(),
        supervisor_id: supervisorId,
      });

      onRunStarted(started.run_id);
      await queryClient.invalidateQueries({ queryKey: ["runs"] });

      setMessage(
        `Started ${testOrderId.trim()} with the saved hybrid monitoring workflow.`,
      );
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not start order.",
      );
    }
  };

  return (
    <>
      <section className="space-y-3 rounded-xl border border-slate-200 p-3">
        <div>
          <p className="text-xs font-bold uppercase tracking-wider text-slate-500">
            Active lifecycle
          </p>
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold"
          />
        </div>

        <div className="grid grid-cols-[1fr_110px] gap-2">
          <select
            value={addType}
            onChange={(event) =>
              setAddType(event.target.value as WorkflowBlockType)
            }
            className="rounded-lg border border-slate-300 px-2 py-2 text-sm"
          >
            {WORKFLOW_BLOCK_TYPES.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>

          <input
            type="number"
            min={1}
            max={blocks.length + 1}
            value={insertAt}
            onChange={(event) =>
              setInsertAt(Math.max(1, Number(event.target.value)))
            }
            className="rounded-lg border border-slate-300 px-2 py-2 text-sm"
            aria-label="Insert position"
          />
        </div>

        <button
          type="button"
          onClick={addBlock}
          className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold"
        >
          + Add block
        </button>
      </section>

      <section className="space-y-3">
        {blocks.map((block, index) => (
          <article
            key={block.id}
            className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm"
          >
            <div className="flex items-start justify-between gap-2">
              <div>
                <span className="rounded-full bg-slate-950 px-2 py-0.5 text-[10px] font-bold text-white">
                  {index + 1}
                </span>
                <p className="mt-2 text-xs font-bold uppercase tracking-wider text-slate-500">
                  {block.block_type.replaceAll("_", " ")}
                </p>
              </div>

              <div className="flex gap-1">
                <button
                  type="button"
                  disabled={index === 0}
                  onClick={() => move(index, -1)}
                  className="rounded border border-slate-300 px-2 py-1 text-xs disabled:opacity-30"
                >
                  ↑
                </button>
                <button
                  type="button"
                  disabled={index === blocks.length - 1}
                  onClick={() => move(index, 1)}
                  className="rounded border border-slate-300 px-2 py-1 text-xs disabled:opacity-30"
                >
                  ↓
                </button>
                <button
                  type="button"
                  onClick={() =>
                    setBlocks((current) =>
                      current.filter((item) => item.id !== block.id),
                    )
                  }
                  className="rounded border border-red-300 px-2 py-1 text-xs text-red-700"
                >
                  ×
                </button>
              </div>
            </div>

            <label className="mt-3 block text-xs font-medium text-slate-600">
              Block label
              <input
                value={block.label}
                onChange={(event) =>
                  updateBlock(block.id, { label: event.target.value })
                }
                className="mt-1 w-full rounded-lg border border-slate-300 px-2 py-2 text-sm text-slate-900"
              />
            </label>

            {block.block_type !== "order_created" &&
            block.block_type !== "delivered" ? (
              <label className="mt-3 block text-xs font-medium text-slate-600">
                Poll/check every (seconds)
                <input
                  type="number"
                  min={1}
                  value={block.wait_seconds}
                  onChange={(event) =>
                    updateBlock(block.id, {
                      wait_seconds: Math.max(
                        1,
                        Number(event.target.value),
                      ),
                    })
                  }
                  className="mt-1 w-full rounded-lg border border-slate-300 px-2 py-2 text-sm text-slate-900"
                />
                <span className="mt-1 block text-[11px] font-normal leading-4 text-slate-400">
                  If an external event arrives earlier, the workflow wakes
                  immediately instead of waiting for this timer.
                </span>
              </label>
            ) : null}

            <label className="mt-3 block text-xs font-medium text-slate-600">
              Gemini instruction for this stage
              <textarea
                value={block.instruction}
                onChange={(event) =>
                  updateBlock(block.id, {
                    instruction: event.target.value,
                  })
                }
                rows={3}
                className="mt-1 w-full rounded-lg border border-slate-300 p-2 text-sm text-slate-900"
              />
            </label>

            {block.block_type === "payment" ? (
              <div className="mt-3 grid grid-cols-2 gap-2 rounded-lg bg-slate-50 p-2">
                <NumberSetting
                  label="Notify payments after failed checks"
                  value={Number(
                    block.settings.notify_after_failures ?? 2,
                  )}
                  onChange={(value) =>
                    updateSetting(
                      block.id,
                      "notify_after_failures",
                      value,
                    )
                  }
                />
                <NumberSetting
                  label="Human review after failed checks"
                  value={Number(
                    block.settings.human_after_failures ?? 3,
                  )}
                  onChange={(value) =>
                    updateSetting(
                      block.id,
                      "human_after_failures",
                      value,
                    )
                  }
                />
              </div>
            ) : null}

            {block.block_type === "shipment" ? (
              <label className="mt-3 flex items-center gap-2 rounded-lg bg-slate-50 p-2 text-xs text-slate-700">
                <input
                  type="checkbox"
                  checked={Boolean(
                    block.settings.notify_fulfillment_when_overdue ?? true,
                  )}
                  onChange={(event) =>
                    updateSetting(
                      block.id,
                      "notify_fulfillment_when_overdue",
                      event.target.checked,
                    )
                  }
                />
                Notify fulfillment if shipment is still not created at a
                scheduled poll.
              </label>
            ) : null}

            {block.block_type === "in_transit" ? (
              <label className="mt-3 flex items-center gap-2 rounded-lg bg-slate-50 p-2 text-xs text-slate-700">
                <input
                  type="checkbox"
                  checked={Boolean(
                    block.settings.human_on_new_delay ?? true,
                  )}
                  onChange={(event) =>
                    updateSetting(
                      block.id,
                      "human_on_new_delay",
                      event.target.checked,
                    )
                  }
                />
                Request human review when a new shipment delay appears.
              </label>
            ) : null}
          </article>
        ))}
      </section>

      {error ? <ErrorState title="Builder action failed" message={error} /> : null}

      {message ? (
        <p className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900">
          {message}
        </p>
      ) : null}

      <section className="space-y-2 rounded-xl border border-slate-200 p-3">
        <button
          type="button"
          onClick={() => void save()}
          disabled={!blocks.length || saveWorkflow.isPending}
          className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold disabled:opacity-50"
        >
          {saveWorkflow.isPending ? "Saving..." : "Save active workflow"}
        </button>

        <div className="border-t border-slate-100 pt-3">
          <p className="text-xs font-bold uppercase tracking-wider text-slate-500">
            Demo order
          </p>
          <input
            value={testOrderId}
            onChange={(event) => setTestOrderId(event.target.value)}
            className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            placeholder="ORDER-DEMO-001"
          />
          <button
            type="button"
            onClick={() => void run()}
            disabled={
              !blocks.length ||
              !testOrderId.trim() ||
              saveWorkflow.isPending ||
              startRun.isPending
            }
            className="mt-2 w-full rounded-lg bg-slate-950 px-3 py-2 text-sm font-semibold text-white disabled:opacity-50"
          >
            {startRun.isPending ? "Starting..." : "Save & run this workflow"}
          </button>
        </div>
      </section>
    </>
  );
}

function NumberSetting({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
}) {
  return (
    <label className="text-[11px] font-medium leading-4 text-slate-600">
      {label}
      <input
        type="number"
        min={1}
        value={value}
        onChange={(event) =>
          onChange(Math.max(1, Number(event.target.value)))
        }
        className="mt-1 w-full rounded border border-slate-300 bg-white px-2 py-1.5 text-sm text-slate-900"
      />
    </label>
  );
}
