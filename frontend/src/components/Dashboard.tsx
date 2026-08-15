"use client";

import { useState } from "react";

import ExecutionLogsPanel from "@/components/ExecutionLogsPanel";
import KanbanBoard from "@/components/KanbanBoard";
import LeftPanel from "@/components/LeftPanel";
import RunInspector from "@/components/RunInspector";
import StartRunModal from "@/components/StartRunModal";

export default function Dashboard() {
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [startModalOpen, setStartModalOpen] = useState(false);

  return (
    <>
      <div className="grid h-screen grid-cols-[390px_minmax(900px,1fr)_420px] overflow-hidden">
        <LeftPanel onRunStarted={setSelectedRunId} />

        <main className="flex min-w-0 flex-col overflow-hidden">
          <div className="min-h-0 flex-1 overflow-auto">
            <KanbanBoard
              selectedRunId={selectedRunId}
              onSelectRun={setSelectedRunId}
              onStartRun={() => setStartModalOpen(true)}
            />
          </div>
          <ExecutionLogsPanel runId={selectedRunId} />
        </main>

        <RunInspector runId={selectedRunId} />
      </div>

      <StartRunModal
        open={startModalOpen}
        onClose={() => setStartModalOpen(false)}
        onStarted={setSelectedRunId}
      />
    </>
  );
}