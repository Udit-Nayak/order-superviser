export type Supervisor = {
  id: string;
  name: string;
  base_instruction: string;
  tools_enabled: string[];
  model_config: {
    model: string;
    temperature?: number;
  };
  created_at: string | null;
};

export type RunStatus =
  | "active"
  | "sleeping"
  | "thinking"
  | "waiting_review"
  | "paused"
  | "post_delivery"
  | "completed"
  | "terminated"
  | "failed";

export type RunListItem = {
  run_id: string;
  supervisor_id: string;
  order_id: string;
  workflow_id: string;
  status: RunStatus;
  next_wake_at: string | null;
  created_at: string | null;
  updated_at: string | null;
  completed_at: string | null;
};

export type TimelineEntry = {
  type: string;
  summary: string;
  payload: Record<string, unknown>;
  created_at: string;
};

export type ExternalOrderState = {
  run_id: string;
  order_id: string;
  payment_status: "pending" | "failed" | "confirmed";
  shipment_status:
    | "not_created"
    | "created"
    | "in_transit"
    | "delayed"
    | "delivered";
  delivery_status: "pending" | "delivered";
  total_delay_hours: number;
  latest_eta: string | null;
  refund_status: "none" | "requested" | "resolved";
  refund_version: number;
  customer_message: string | null;
  customer_message_version: number;
  updated_at: string | null;
};

export type ExternalOrderStatePatch = {
  payment_status?: "pending" | "failed" | "confirmed";
  shipment_status?:
    | "not_created"
    | "created"
    | "in_transit"
    | "delayed"
    | "delivered";
  delivery_status?: "pending" | "delivered";
  additional_delay_hours?: number;
  latest_eta?: string;
  refund_status?: "none" | "requested" | "resolved";
  customer_message?: string;
  instruction?: string;
};

export type WorkflowBlockType =
  | "order_created"
  | "payment"
  | "shipment"
  | "in_transit"
  | "delivered"
  | "post_delivery";

export type WorkflowBlock = {
  id: string;
  block_type: WorkflowBlockType;
  label: string;
  wait_seconds: number;
  instruction: string;
  settings: Record<string, unknown>;
  enabled?: boolean;
};

export type WorkflowTemplate = {
  id: string;
  supervisor_id: string;
  name: string;
  blocks: WorkflowBlock[];
  active: boolean;
  created_at: string | null;
  updated_at: string | null;
};

export type BlockHistoryItem = {
  id: string;
  label: string;
  block_type: WorkflowBlockType;
  completed_at?: string;
  reason?: string;
};

export type FinalSummary = {
  summary: string;
  actions_taken: string[];
  key_learnings: string[];
  recommendations: string[];
  created_at?: string;
};

export type RunDetail = {
  run_id: string;
  order_id: string;
  supervisor_id?: string;
  status: RunStatus;
  source?: "temporal" | "supabase";
  timeline: TimelineEntry[];
  memory_summary: string;
  key_facts: Record<string, unknown>;
  instructions: string[];
  external_state?: Partial<ExternalOrderState>;
  next_wake_at: string | null;
  terminal?: boolean;
  pending_event_count?: number;
  human_intervention_required?: boolean;
  current_block?: WorkflowBlock | null;
  block_history?: BlockHistoryItem[];
  workflow_template_name?: string;
  final_summary?: FinalSummary | null;
};

export type CreateSupervisorInput = {
  name: string;
  base_instruction: string;
  tools_enabled: string[];
  model_config: {
    model: string;
    temperature: number;
  };
};

export type StartRunInput = {
  order_id: string;
  supervisor_id: string;
};

export type SaveWorkflowTemplateInput = {
  name: string;
  supervisor_id: string;
  blocks: WorkflowBlock[];
  active: boolean;
};
