"use client";

import { useState } from "react";

import SupervisorPanel from "@/components/SupervisorPanel";
import WorkflowBuilder from "@/components/WorkflowBuilder";

export default function LeftPanel({
  onRunStarted,
}: {
  onRunStarted: (runId: string) => void;
}) {
  const [tab, setTab] = useState<"setup" | "builder">("setup");

  return (
    <aside className="flex h-screen min-h-195 flex-col border-r border-slate-200 bg-white">
      <div className="border-b border-slate-200 p-4">
        <p className="text-xs font-bold uppercase tracking-wider text-slate-500">
          Order supervisor
        </p>
        <h2 className="mt-1 text-xl font-bold">
          {tab === "setup" ? "Setup" : "Default workflow builder"}
        </h2>

        <div className="mt-4 grid grid-cols-2 rounded-lg bg-slate-100 p-1 text-sm">
          <button
            type="button"
            onClick={() => setTab("setup")}
            className={`rounded-md px-3 py-2 font-medium ${
              tab === "setup" ? "bg-white shadow-sm" : "text-slate-500"
            }`}
          >
            Setup
          </button>
          <button
            type="button"
            onClick={() => setTab("builder")}
            className={`rounded-md px-3 py-2 font-medium ${
              tab === "builder" ? "bg-white shadow-sm" : "text-slate-500"
            }`}
          >
            Builder
          </button>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {tab === "setup" ? (
          <SupervisorPanel />
        ) : (
          <WorkflowBuilder onRunStarted={onRunStarted} />
        )}
      </div>
    </aside>
  );
}