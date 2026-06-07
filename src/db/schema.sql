-- GTM Personalized Outreach Engine — Supabase schema. See architecture.md §11.
-- Run this in the Supabase SQL editor (Phase 1).

create table if not exists seller_profile (   -- single row; what we sell (set once, reused per run)
  id int primary key default 1,
  product_description text,
  value_prop text,
  default_tone text,
  updated_at timestamptz default now()
);

create table if not exists runs (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz default now(),
  prospect_name text,
  company text not null,
  company_key text not null,
  mode text default 'personalized',
  product_description text,
  outreach_goal text,
  extra_context text,
  status text,
  flags jsonb default '[]',
  signal_freshness text,
  chosen_signal_id uuid,
  approval_status text default 'draft'
);
create index if not exists idx_runs_company_key on runs (company_key);  -- powers account_collision

create table if not exists research_sources (
  id uuid primary key default gen_random_uuid(),
  run_id uuid references runs(id),
  query_hash text,
  category text,
  title text,
  url text,
  snippet text,
  published_date date,
  age_days int,
  raw jsonb,
  created_at timestamptz default now()
);

create table if not exists signals (
  id uuid primary key default gen_random_uuid(),
  run_id uuid references runs(id),
  type text,
  description text,
  source_url text,
  published_date date,
  age_days int,
  funding_meta jsonb,
  recency int,
  specificity int,
  actionability int,
  confidence int,
  total_score numeric,
  reasoning text,
  is_sensitive bool default false,
  hook_sentence text,
  created_at timestamptz default now()
);

create table if not exists hooks (
  id uuid primary key default gen_random_uuid(),
  run_id uuid references runs(id),
  signal_id uuid references signals(id),
  hook_text text,
  why_it_matters text,
  why_chosen text,
  why_alternatives_rejected jsonb,
  created_at timestamptz default now()
);

create table if not exists drafts (
  id uuid primary key default gen_random_uuid(),
  run_id uuid references runs(id),
  channel text,
  version int default 1,
  subject text,
  body text,
  tone text,
  is_approved bool default false,
  created_at timestamptz default now()
);

create table if not exists human_actions (
  id uuid primary key default gen_random_uuid(),
  run_id uuid references runs(id),
  stage text,
  action text,
  payload jsonb,
  created_at timestamptz default now()
);
