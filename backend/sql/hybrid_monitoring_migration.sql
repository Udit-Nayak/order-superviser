-- HYBRID EVENT + POLLING UPDATE
-- Run this ONCE in the Supabase SQL Editor before starting the new worker.

create extension if not exists pgcrypto;

-- 1) Builder workflow storage (safe if you already ran the previous migration).
create table if not exists public.workflow_templates (
    id uuid primary key default gen_random_uuid(),
    supervisor_id uuid not null references public.supervisors(id) on delete cascade,
    name varchar(200) not null,
    blocks jsonb not null default '[]'::jsonb,
    active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists ix_workflow_templates_supervisor_id
    on public.workflow_templates(supervisor_id);
create index if not exists ix_workflow_templates_active
    on public.workflow_templates(active);

-- 2) Demo external source-of-truth.
-- This stands in for Amazon + payment gateway + warehouse + courier APIs.
create table if not exists public.order_runtime_states (
    run_id uuid primary key references public.runs(id) on delete cascade,
    order_id text not null,
    payment_status text not null default 'pending'
        check (payment_status in ('pending', 'failed', 'confirmed')),
    shipment_status text not null default 'not_created'
        check (shipment_status in ('not_created', 'created', 'in_transit', 'delayed', 'delivered')),
    delivery_status text not null default 'pending'
        check (delivery_status in ('pending', 'delivered')),
    total_delay_hours double precision not null default 0,
    latest_eta timestamptz null,
    refund_status text not null default 'none'
        check (refund_status in ('none', 'requested', 'resolved')),
    refund_version integer not null default 0,
    customer_message text null,
    customer_message_version integer not null default 0,
    updated_at timestamptz not null default now()
);

create index if not exists idx_order_runtime_states_order_id
    on public.order_runtime_states(order_id);

-- 3) The previous Phase-2 DB constraint did not know about the newer UI/log types.
-- Your current error with `workflow_block` is fixed here.
alter table public.timeline_entries
    drop constraint if exists timeline_entries_type_check;

alter table public.timeline_entries
    add constraint timeline_entries_type_check
    check (type in (
        'event',
        'agent_decision',
        'tool_call',
        'system',
        'instruction',
        'workflow_block',
        'human_action',
        'state_poll'
    ));

-- 4) The old runs constraint also did not contain post_delivery.
alter table public.runs
    drop constraint if exists runs_status_check;

alter table public.runs
    add constraint runs_status_check
    check (status in (
        'active',
        'sleeping',
        'thinking',
        'waiting_review',
        'paused',
        'post_delivery',
        'completed',
        'terminated',
        'failed'
    ));
