-- Replace YOUR_RUN_ID with the run UUID printed by phase2_test.ps1.

select *
from public.runs
where id = '70f06263-ffb7-419b-a58b-564cbbbe5d33'::uuid;

select type, summary, payload, created_at
from public.timeline_entries
where run_id = '70f06263-ffb7-419b-a58b-564cbbbe5d33'::uuid
order by created_at;

select *
from public.memory_snapshots
where run_id = '70f06263-ffb7-419b-a58b-564cbbbe5d33'::uuid;

select *
from public.instructions
where run_id = '70f06263-ffb7-419b-a58b-564cbbbe5d33'::uuid
order by created_at;

select *
from public.final_summaries
where run_id = '70f06263-ffb7-419b-a58b-564cbbbe5d33'::uuid;
