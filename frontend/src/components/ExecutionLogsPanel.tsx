"use client";

import { useMemo, useState } from "react";

import ErrorState from "@/components/ErrorState";
import { useRunDetail } from "@/hooks/useOrderSupervisor";

export default function ExecutionLogsPanel({
  runId,
}: {
  runId: string | null;
}) {
  const run = useRunDetail(runId);
  const [filter, setFilter] = useState("all");
  const [selected, setSelected] = useState<number | null>(null);

  const entries = useMemo(() => {
    // Copy first, then reverse so React Query's cached array is not mutated.
    const timeline = [...(run.data?.timeline ?? [])].reverse();

    return filter === "all"
      ? timeline
      : timeline.filter((item) => item.type === filter);
  }, [filter, run.data?.timeline]);

  return (
    <section className="border-t border-slate-200 bg-slate-950 text-slate-100">
      <div className="flex items-center justify-between border-b border-slate-800 px-4 py-2">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">
            Execution
          </p>
          <h3 className="text-sm font-bold">
            {run.data ? `${run.data.order_id} logs` : "Workflow logs"}
          </h3>
        </div>

        <select
          value={filter}
          onChange={(event) => {
            setFilter(event.target.value);
            setSelected(null);
          }}
          className="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs"
        >
          <option value="all">All logs</option>
          <option value="state_poll">External-state polls</option>
          <option value="workflow_block">Workflow blocks</option>
          <option value="event">External events</option>
          <option value="agent_decision">AI decisions</option>
          <option value="tool_call">Tool calls</option>
          <option value="human_action">Human actions</option>
          <option value="instruction">Instructions</option>
          <option value="system">System</option>
        </select>
      </div>

      {!runId ? (
        <p className="p-5 text-sm text-slate-400">
          Select an order to inspect its execution logs.
        </p>
      ) : run.error ? (
        <div className="bg-white p-4 text-slate-900">
          <ErrorState
            message={run.error.message}
            onRetry={() => void run.refetch()}
          />
        </div>
      ) : (
        <div className="grid h-[250px] grid-cols-[minmax(0,1fr)_360px]">
          <div className="overflow-y-auto">
            {entries.map((entry, index) => (
              <button
                key={`${entry.created_at}-${index}`}
                type="button"
                onClick={() => setSelected(index)}
                className={`grid w-full grid-cols-[150px_150px_1fr] gap-3 border-b border-slate-800 px-4 py-2 text-left text-xs ${
                  selected === index ? "bg-slate-800" : "hover:bg-slate-900"
                }`}
              >
                <time className="text-slate-400">
                  {new Date(entry.created_at).toLocaleTimeString()}
                </time>
                <span className="font-semibold uppercase text-slate-300">
                  {entry.type.replaceAll("_", " ")}
                </span>
                <span className="truncate">{entry.summary}</span>
              </button>
            ))}

            {!entries.length ? (
              <p className="p-5 text-sm text-slate-500">
                No matching logs yet.
              </p>
            ) : null}
          </div>

          <div className="overflow-y-auto border-l border-slate-800 bg-slate-900 p-3">
            {selected !== null && entries[selected] ? (
              <>
                <p className="text-xs font-bold uppercase text-slate-400">
                  Selected log
                </p>
                <p className="mt-2 text-sm">{entries[selected].summary}</p>
                <pre className="mt-3 whitespace-pre-wrap break-words rounded bg-slate-950 p-2 text-[11px] text-slate-300">
                  {JSON.stringify(entries[selected].payload, null, 2)}
                </pre>
              </>
            ) : (
              <p className="text-xs text-slate-500">
                Click a log row to inspect its structured details. Timer-driven
                polling is easiest to verify with the External-state polls
                filter.
              </p>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
