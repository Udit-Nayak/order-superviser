"use client";

import { FormEvent, useState } from "react";

import ErrorState from "@/components/ErrorState";
import { useCreateSupervisor } from "@/hooks/useOrderSupervisor";
import { TOOL_OPTIONS } from "@/lib/constants";

export default function SupervisorPanel() {
  const createSupervisor = useCreateSupervisor();

  const [name, setName] = useState("Delivery Operations AI");
  const [baseInstruction, setBaseInstruction] = useState(
    "Monitor the order from creation through post-delivery support. Follow the saved workflow blocks. Use only enabled tools and request human intervention for risky or unresolved cases.",
  );
  const [tools, setTools] = useState<string[]>(
    TOOL_OPTIONS.map((item) => item.name),
  );
  const [success, setSuccess] = useState("");

  const toggle = (tool: string) => {
    setTools((current) =>
      current.includes(tool)
        ? current.filter((item) => item !== tool)
        : [...current, tool],
    );
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setSuccess("");

    try {
      const created = await createSupervisor.mutateAsync({
        name: name.trim(),
        base_instruction: baseInstruction.trim(),
        tools_enabled: tools,
        model_config: {
          model: "gemini-3.6-flash",
          temperature: 0.2,
        },
      });
      setSuccess(
        `Created "${created.name}" with the generalized default workflow.`,
      );
    } catch {
      // Error rendered below.
    }
  };

  return (
    <form onSubmit={submit} className="space-y-5 p-5">
      
      <label className="block">
        <span className="text-sm font-medium">Supervisor name</span>
        <input
          value={name}
          onChange={(event) => setName(event.target.value)}
          required
          className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
        />
      </label>

      <label className="block">
        <span className="text-sm font-medium">Base instruction</span>
        <textarea
          value={baseInstruction}
          onChange={(event) => setBaseInstruction(event.target.value)}
          required
          rows={7}
          className="mt-1 w-full rounded-lg border border-slate-300 p-3"
        />
      </label>

      <div>
        <p className="text-sm font-medium">Allowed actions</p>
        <div className="mt-2 space-y-2">
          {TOOL_OPTIONS.map((tool) => (
            <label
              key={tool.name}
              className="flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-sm"
            >
              <input
                type="checkbox"
                checked={tools.includes(tool.name)}
                onChange={() => toggle(tool.name)}
              />
              {tool.label}
            </label>
          ))}
        </div>
      </div>

      {createSupervisor.error ? (
        <ErrorState
          title="Could not create supervisor"
          message={createSupervisor.error.message}
        />
      ) : null}

      {success ? (
        <p className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">
          {success}
        </p>
      ) : null}

      <button
        type="submit"
        disabled={
          createSupervisor.isPending ||
          !name.trim() ||
          !baseInstruction.trim() ||
          tools.length === 0
        }
        className="w-full rounded-lg bg-slate-950 px-4 py-2.5 font-semibold text-white"
      >
        {createSupervisor.isPending ? "Creating..." : "Create supervisor"}
      </button>
    </form>
  );
}