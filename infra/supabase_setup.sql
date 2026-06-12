-- MindSafe Supabase Setup
-- Run this in: Supabase Dashboard → SQL Editor → New query → Run
-- Or via CLI: supabase db push (if using local CLI)

-- ============================================================
-- 1. video_eval table (cache + history)
-- ============================================================

create table if not exists public.video_eval (
    id                      bigserial primary key,
    video_path              text        not null unique,   -- YouTube URL (pseudonymized in logs, raw here)
    child_age               numeric(4,1),                  -- e.g. 4.0
    age_band                text,                          -- band key, e.g. "G4_5_8"
    age_band_name           text,                          -- "Preschool (3-5)"
    duration_seconds        numeric,
    duration_minutes        numeric,
    dev_score               numeric(5,2),                  -- 0–100
    dev_interpretation      text,
    brainrot_index          numeric(5,2),                  -- 0–100
    brainrot_interpretation text,
    overall_recommendation  text,
    dimension_scores        jsonb,                         -- {"pacing": 72.0, "story": 85.0, ...}
    metrics                 jsonb,                         -- raw 30+ heuristic metrics
    strengths               jsonb,                         -- array of strings
    concerns                jsonb,                         -- array of strings
    recommendations         jsonb,                         -- array of strings
    created_at              timestamptz default now(),
    updated_at              timestamptz default now()
);

-- ============================================================
-- 2. Indexes for common query patterns
-- ============================================================

-- Cache lookup by URL (primary use: _get_cached in api.py)
create index if not exists idx_video_eval_video_path
    on public.video_eval (video_path);

-- Frontend history page: sort by recent
create index if not exists idx_video_eval_created_at
    on public.video_eval (created_at desc);

-- Filter by age band (for analytics/dashboard)
create index if not exists idx_video_eval_age_band
    on public.video_eval (age_band);

-- ============================================================
-- 3. Auto-update updated_at on row change
-- ============================================================

create or replace function public.set_updated_at()
returns trigger language plpgsql as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

create or replace trigger trg_video_eval_updated_at
    before update on public.video_eval
    for each row execute function public.set_updated_at();

-- ============================================================
-- 4. Row Level Security (RLS)
-- ============================================================
-- The API uses the service_role key (bypasses RLS).
-- The frontend uses the anon key — read-only is fine for history page.
-- Disable public write via anon key.

alter table public.video_eval enable row level security;

-- Allow anon read (frontend history page)
create policy "anon can read evaluations"
    on public.video_eval
    for select
    to anon
    using (true);

-- Block anon write (only service_role / backend can insert/update)
create policy "service_role can write evaluations"
    on public.video_eval
    for all
    to service_role
    using (true)
    with check (true);

-- ============================================================
-- 5. Verify setup
-- ============================================================
-- Run this after the above to confirm:
--
--   select column_name, data_type
--   from information_schema.columns
--   where table_name = 'video_eval'
--   order by ordinal_position;
