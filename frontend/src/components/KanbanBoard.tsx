"use client";

import ErrorState from "@/components/ErrorState";
import { useRuns, useSupervisors } from "@/hooks/useOrderSupervisor";
import type { RunListItem, RunStatus } from "@/lib/types";

type Props = {
  selectedRunId: string | null;
  onSelectRun: (runId: string) => void;
  onStartRun: () => void;
};

type ColumnId =
  | "sleeping"
  | "thinking"
  | "waiting_review"
  | "post_delivery"
  | "completed";

const COLUMNS: Array<{
  id: ColumnId;
  label: string;
  description: string;
}> = [
  {
    id: "sleeping",
    label: "Monitoring / sleeping",
    description: "Waiting for an event or next scheduled poll",
  },
  {
    id: "thinking",
    label: "AI thinking",
    description: "Short-lived Gemini/activity processing",
  },
  {
    id: "waiting_review",
    label: "Human review",
    description: "Automation intentionally waiting for an operator",
  },
  {
    id: "post_delivery",
    label: "Delivered / support",
    description: "Post-delivery monitoring window",
  },
  {
    id: "completed",
    label: "Completed",
    description: "Finished, terminated, or failed",
  },
];

function columnFor(status: RunStatus): ColumnId {
  if (status === "active") return "thinking";
  if (status === "terminated" || status === "failed") return "completed";
  if (status === "paused") return "waiting_review";
  return status;
}

function formatWake(value: string | null) {
  return value
    ? `Next poll: ${new Date(value).toLocaleString()}`
    : "No scheduled poll";
}

function RunCard({
  run,
  supervisorName,
  selected,
  onClick,
}: {
  run: RunListItem;
  supervisorName: string;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`w-full rounded-xl border p-3 text-left shadow-sm transition ${
        selected
          ? "border-slate-950 bg-slate-950 text-white"
          : "border-slate-200 bg-white hover:border-slate-400"
      }`}
    >
      <p className="font-bold">{run.order_id}</p>

      <p
        className={`mt-1 text-xs ${
          selected ? "text-slate-300" : "text-slate-500"
        }`}
      >
        {supervisorName}
      </p>

      <p
        className={`mt-3 text-xs ${
          selected ? "text-slate-300" : "text-slate-500"
        }`}
      >
        {formatWake(run.next_wake_at)}
      </p>

      <p
        className={`mt-2 text-[11px] uppercase tracking-wide ${
          selected ? "text-slate-300" : "text-slate-400"
        }`}
      >
        {run.status === "sleeping"
          ? "monitoring"
          : run.status.replaceAll("_", " ")}
      </p>
    </button>
  );
}

export default function KanbanBoard({
  selectedRunId,
  onSelectRun,
  onStartRun,
}: Props) {
  const runs = useRuns();
  const supervisors = useSupervisors();

  const supervisorNames = new Map(
    (supervisors.data ?? []).map((item) => [item.id, item.name]),
  );

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col bg-slate-50">
      {/* Header stays fixed while the kanban body fills all remaining space */}
      <div className="shrink-0 flex items-center justify-between border-b border-slate-200 bg-white px-5 py-4">
        <div>
          <p className="text-xs font-bold uppercase tracking-wider text-slate-500">
            Live orders
          </p>
          <h1 className="text-xl font-bold">Order kanban</h1>
        </div>

        <button
          type="button"
          onClick={onStartRun}
          className="rounded-lg bg-slate-950 px-4 py-2 text-sm font-semibold text-white"
        >
          + Start new run
        </button>
      </div>

      {/* This section expands to consume all space above ExecutionLogsPanel */}
      <div className="min-h-0 flex-1 p-4">
        {runs.error ? (
          <ErrorState
            message={runs.error.message}
            onRetry={() => void runs.refetch()}
          />
        ) : runs.isLoading ? (
          <div className="h-full rounded-xl border border-slate-200 bg-white p-5 text-sm text-slate-500">
            Loading orders...
          </div>
        ) : (
          <div className="grid h-full min-h-0 min-w-[900px] grid-cols-5 gap-3 overflow-x-auto">
            {COLUMNS.map((column) => {
              const items = (runs.data ?? []).filter(
                (run) => columnFor(run.status) === column.id,
              );

              return (
                <section
                  key={column.id}
                  className="flex h-full min-h-0 flex-col overflow-hidden rounded-xl border border-slate-200 bg-slate-100/70"
                >
                  {/* Column header */}
                  <div className="shrink-0 border-b border-slate-200 px-3 py-3">
                    <div className="flex items-center justify-between">
                      <h2 className="text-sm font-bold">{column.label}</h2>

                      <span className="rounded-full bg-white px-2 py-0.5 text-xs text-slate-500">
                        {items.length}
                      </span>
                    </div>

                    <p className="mt-1 text-[10px] leading-4 text-slate-400">
                      {column.description}
                    </p>
                  </div>

                  {/* Cards scroll inside their own full-height column */}
                  <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-3">
                    {items.map((run) => (
                      <RunCard
                        key={run.run_id}
                        run={run}
                        supervisorName={
                          supervisorNames.get(run.supervisor_id) ??
                          "Unknown supervisor"
                        }
                        selected={selectedRunId === run.run_id}
                        onClick={() => onSelectRun(run.run_id)}
                      />
                    ))}

                    {!items.length ? (
                      <div className="flex h-full min-h-[100px] items-center justify-center">
                        <p className="text-center text-xs text-slate-400">
                          No orders
                        </p>
                      </div>
                    ) : null}
                  </div>
                </section>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}