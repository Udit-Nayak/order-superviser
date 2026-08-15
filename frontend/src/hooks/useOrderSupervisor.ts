"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type {
  CreateSupervisorInput,
  ExternalOrderStatePatch,
  SaveWorkflowTemplateInput,
  StartRunInput,
} from "@/lib/types";

export function useSupervisors() {
  return useQuery({
    queryKey: ["supervisors"],
    queryFn: api.listSupervisors,
  });
}

export function useActiveWorkflow(supervisorId: string | null) {
  return useQuery({
    queryKey: ["workflow-template", supervisorId],
    queryFn: () => api.getActiveWorkflow(supervisorId as string),
    enabled: Boolean(supervisorId),
  });
}

export function useRuns() {
  return useQuery({
    queryKey: ["runs"],
    queryFn: api.listRuns,
    refetchInterval: 1000,
  });
}

export function useRunDetail(runId: string | null) {
  return useQuery({
    queryKey: ["run", runId],
    queryFn: () => api.getRun(runId as string),
    enabled: Boolean(runId),
    refetchInterval: 1000,
  });
}

export function useExternalOrderState(runId: string | null) {
  return useQuery({
    queryKey: ["external-state", runId],
    queryFn: () => api.getExternalState(runId as string),
    enabled: Boolean(runId),
    refetchInterval: 1000,
  });
}

export function useFinalSummary(runId: string | null, enabled: boolean) {
  return useQuery({
    queryKey: ["final-summary", runId],
    queryFn: () => api.getFinalSummary(runId as string),
    enabled: Boolean(runId) && enabled,
    retry: false,
    refetchInterval: enabled ? 1500 : false,
  });
}

export function useCreateSupervisor() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: CreateSupervisorInput) => api.createSupervisor(input),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["supervisors"] });
    },
  });
}

export function useSaveWorkflow() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: SaveWorkflowTemplateInput) => api.saveWorkflow(input),
    onSuccess: async (saved) => {
      await queryClient.invalidateQueries({
        queryKey: ["workflow-template", saved.supervisor_id],
      });
    },
  });
}

export function useStartRun() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: StartRunInput) => api.startRun(input),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["runs"] });
    },
  });
}

export function useRunActions(runId: string | null) {
  const queryClient = useQueryClient();

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["runs"] }),
      queryClient.invalidateQueries({ queryKey: ["run", runId] }),
      queryClient.invalidateQueries({ queryKey: ["external-state", runId] }),
    ]);
  };

  return {
    updateExternalState: useMutation({
      mutationFn: (patch: ExternalOrderStatePatch) =>
        api.updateExternalState(runId as string, patch),
      onSuccess: refresh,
    }),

    // Backwards-compatible raw event endpoint. The dashboard simulator should
    // normally use updateExternalState so scheduled polls can observe the same
    // state later.
    sendEvent: useMutation({
      mutationFn: ({
        eventType,
        payload,
        instruction,
      }: {
        eventType: string;
        payload: Record<string, unknown>;
        instruction?: string;
      }) =>
        api.sendEvent(
          runId as string,
          eventType,
          payload,
          instruction,
        ),
      onSuccess: refresh,
    }),

    addInstruction: useMutation({
      mutationFn: (text: string) => api.addInstruction(runId as string, text),
      onSuccess: refresh,
    }),

    humanAction: useMutation({
      mutationFn: (text: string) => api.humanAction(runId as string, text),
      onSuccess: refresh,
    }),

    interrupt: useMutation({
      mutationFn: () => api.interruptRun(runId as string),
      onSuccess: refresh,
    }),

    terminate: useMutation({
      mutationFn: () => api.terminateRun(runId as string),
      onSuccess: refresh,
    }),
  };
}
