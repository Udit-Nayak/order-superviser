create extension if not exists pgcrypto;

create table if not exists public.supervisors (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    base_instruction text not null,
    tools_enabled text[] not null default '{}',
    wake_aggressiveness text not null default 'medium'
        check (wake_aggressiveness in ('low', 'medium', 'high')),
    model_config jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create table if not exists public.runs (
    id uuid primary key,
    supervisor_id uuid not null references public.supervisors(id) on delete restrict,
    order_id text not null,
    workflow_id text not null unique,
    status text not null default 'active'
        check (status in (
            'active', 'sleeping', 'thinking', 'waiting_review',
            'paused', 'completed', 'terminated', 'failed'
        )),
    next_wake_at timestamptz null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    completed_at timestamptz null
);

create index if not exists idx_runs_order_id on public.runs(order_id);
create index if not exists idx_runs_status on public.runs(status);

create table if not exists public.timeline_entries (
    id uuid primary key default gen_random_uuid(),
    run_id uuid not null references public.runs(id) on delete cascade,
    type text not null
        check (type in ('event', 'agent_decision', 'tool_call', 'system', 'instruction')),
    payload jsonb not null default '{}'::jsonb,
    summary text not null,
    created_at timestamptz not null default now()
);

create index if not exists idx_timeline_run_created
    on public.timeline_entries(run_id, created_at);

create table if not exists public.memory_snapshots (
    run_id uuid primary key references public.runs(id) on delete cascade,
    summary text not null default '',
    key_facts jsonb not null default '{}'::jsonb,
    updated_at timestamptz not null default now()
);

create table if not exists public.instructions (
    id uuid primary key default gen_random_uuid(),
    run_id uuid not null references public.runs(id) on delete cascade,
    text text not null,
    active boolean not null default true,
    created_at timestamptz not null default now()
);

create index if not exists idx_instructions_run_created
    on public.instructions(run_id, created_at);

create table if not exists public.final_summaries (
    run_id uuid primary key references public.runs(id) on delete cascade,
    summary text not null,
    actions_taken jsonb not null default '[]'::jsonb,
    key_learnings jsonb not null default '[]'::jsonb,
    recommendations jsonb not null default '[]'::jsonb,
    created_at timestamptz not null default now()
);


-- Run once in Supabase SQL Editor after applying this update.

create table if not exists workflow_templates (
    id uuid primary key,
    supervisor_id uuid not null references supervisors(id) on delete cascade,
    name varchar(200) not null,
    blocks jsonb not null default '[]'::jsonb,
    active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists ix_workflow_templates_supervisor_id
    on workflow_templates(supervisor_id);

create index if not exists ix_workflow_templates_active
    on workflow_templates(active);