"use client";

import { FormEvent, useState } from "react";

import ErrorState from "@/components/ErrorState";
import {
  useActiveWorkflow,
  useStartRun,
  useSupervisors,
} from "@/hooks/useOrderSupervisor";

type Props = {
  open: boolean;
  onClose: () => void;
  onStarted: (runId: string) => void;
};

export default function StartRunModal({ open, onClose, onStarted }: Props) {
  const supervisors = useSupervisors();
  const startRun = useStartRun();

  const [supervisorId, setSupervisorId] = useState("");
  const [orderId, setOrderId] = useState("");

  // Derive the first supervisor as the default instead of synchronously
  // setting state inside useEffect.
  const effectiveSupervisorId =
    supervisorId || supervisors.data?.[0]?.id || "";

  const activeWorkflow = useActiveWorkflow(
    effectiveSupervisorId || null,
  );

  if (!open) return null;

  const submit = async (event: FormEvent) => {
    event.preventDefault();

    if (!effectiveSupervisorId || !orderId.trim()) return;

    try {
      const created = await startRun.mutateAsync({
        supervisor_id: effectiveSupervisorId,
        order_id: orderId.trim(),
      });

      onStarted(created.run_id);
      setOrderId("");
      onClose();
    } catch {
      // Error is rendered below.
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/45 p-4">
      <div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs font-bold uppercase tracking-wider text-slate-500">
              Order
            </p>
            <h2 className="text-xl font-bold">Start new run</h2>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="rounded px-3 py-1 text-xl text-slate-500"
          >
            ×
          </button>
        </div>

        <form onSubmit={submit} className="mt-5 space-y-4">
          <label className="block">
            <span className="text-sm font-medium">Supervisor</span>
            <select
              value={effectiveSupervisorId}
              onChange={(event) => setSupervisorId(event.target.value)}
              required
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
            >
              {(supervisors.data ?? []).map((supervisor) => (
                <option key={supervisor.id} value={supervisor.id}>
                  {supervisor.name}
                </option>
              ))}
            </select>
          </label>

          <label className="block">
            <span className="text-sm font-medium">Order ID</span>
            <input
              value={orderId}
              onChange={(event) => setOrderId(event.target.value)}
              placeholder="ORDER-DEMO-001"
              required
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
            />
          </label>

          <div className="rounded-xl border border-blue-200 bg-blue-50 p-3 text-sm text-blue-950">
            <p className="font-semibold">Workflow used automatically</p>
            <p className="mt-1">
              {activeWorkflow.isLoading
                ? "Loading active workflow..."
                : activeWorkflow.data?.name ?? "Generalized default workflow"}
            </p>
            <p className="mt-2 text-xs leading-5">
              External events wake the order immediately. If no event arrives,
              Temporal wakes at the current Builder block&apos;s poll interval
              and independently checks the external order state.
            </p>
          </div>

          {startRun.error ? (
            <ErrorState
              title="Could not start order"
              message={startRun.error.message}
            />
          ) : null}

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-slate-300 px-4 py-2 font-medium"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={
                startRun.isPending ||
                !effectiveSupervisorId ||
                !orderId.trim()
              }
              className="rounded-lg bg-slate-950 px-4 py-2 font-semibold text-white disabled:opacity-50"
            >
              {startRun.isPending ? "Starting..." : "Start run"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
