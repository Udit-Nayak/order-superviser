import type {
  CreateSupervisorInput,
  ExternalOrderState,
  ExternalOrderStatePatch,
  FinalSummary,
  RunDetail,
  RunListItem,
  SaveWorkflowTemplateInput,
  StartRunInput,
  Supervisor,
  WorkflowTemplate,
} from "./types";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ??
  "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    let detail = `Request failed with HTTP ${response.status}`;
    try {
      const body = await response.json();
      detail =
        typeof body?.detail === "string"
          ? body.detail
          : body?.detail
            ? JSON.stringify(body.detail)
            : detail;
    } catch {
      // Keep fallback message.
    }
    throw new ApiError(response.status, detail);
  }

  return response.status === 204
    ? (undefined as T)
    : (response.json() as Promise<T>);
}

export const api = {
  listSupervisors: () => request<Supervisor[]>("/api/supervisors"),

  createSupervisor: (input: CreateSupervisorInput) =>
    request<Supervisor>("/api/supervisors", {
      method: "POST",
      body: JSON.stringify(input),
    }),

  getActiveWorkflow: (supervisorId: string) =>
    request<WorkflowTemplate>(
      `/api/workflow-templates/active?supervisor_id=${encodeURIComponent(supervisorId)}`,
    ),

  saveWorkflow: (input: SaveWorkflowTemplateInput) =>
    request<WorkflowTemplate>("/api/workflow-templates", {
      method: "POST",
      body: JSON.stringify(input),
    }),

  listRuns: () => request<RunListItem[]>("/api/runs"),

  getRun: (runId: string) => request<RunDetail>(`/api/runs/${runId}`),

  startRun: (input: StartRunInput) =>
    request<{
      run_id: string;
      order_id: string;
      workflow_id: string;
      supervisor_id: string;
      workflow_template_id: string;
      workflow_template_name: string;
      status: string;
    }>("/api/runs", {
      method: "POST",
      body: JSON.stringify(input),
    }),

  getExternalState: (runId: string) =>
    request<ExternalOrderState>(`/api/runs/${runId}/external-state`),

  updateExternalState: (runId: string, patch: ExternalOrderStatePatch) =>
    request<{
      accepted: boolean;
      run_id: string;
      event_type: string;
      state: ExternalOrderState;
    }>(`/api/runs/${runId}/external-state`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),

  // Kept for API/CLI compatibility. The UI now prefers updateExternalState().
  sendEvent: (
    runId: string,
    eventType: string,
    payload: Record<string, unknown>,
    instruction?: string,
  ) =>
    request<{ accepted: boolean; run_id: string; event_type: string }>(
      `/api/runs/${runId}/events`,
      {
        method: "POST",
        body: JSON.stringify({
          type: eventType,
          payload,
          instruction: instruction?.trim() || null,
        }),
      },
    ),

  addInstruction: (runId: string, text: string) =>
    request<{ accepted: boolean; run_id: string }>(
      `/api/runs/${runId}/instructions`,
      {
        method: "POST",
        body: JSON.stringify({ text }),
      },
    ),

  humanAction: (runId: string, text: string) =>
    request<{ accepted: boolean; run_id: string }>(
      `/api/runs/${runId}/human-action`,
      {
        method: "POST",
        body: JSON.stringify({ text }),
      },
    ),

  interruptRun: (runId: string) =>
    request<{ accepted: boolean; status: string }>(
      `/api/runs/${runId}/interrupt`,
      { method: "POST" },
    ),

  terminateRun: (runId: string) =>
    request<{ accepted: boolean }>(`/api/runs/${runId}/terminate`, {
      method: "POST",
    }),

  getFinalSummary: (runId: string) =>
    request<FinalSummary & { run_id: string }>(
      `/api/runs/${runId}/final-summary`,
    ),
};
