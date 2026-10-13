-- Application tables for the n8n automation hub. n8n's own tables live in schema "n8n".
create schema if not exists n8n;
create schema if not exists hub;

create table if not exists hub.leads (
  idempotency_key text primary key,
  email           text not null,
  name            text,
  company         text,
  country         text,
  phone           text,
  score           int  not null,
  tier            text not null check (tier in ('hot','warm','cold')),
  reasons         jsonb not null default '[]',
  source          text default 'webhook',
  created_at      timestamptz not null default now()
);

create table if not exists hub.tickets (
  idempotency_key text primary key,
  subject         text,
  message         text not null,
  category        text not null,
  urgency         text not null,
  draft_reply     text,
  classifier      text not null check (classifier in ('llm','fallback')),
  fallback_reason text,
  created_at      timestamptz not null default now()
);

create table if not exists hub.prices (
  book_id    text primary key,
  title      text not null,
  price_gbp  numeric(8,2) not null,
  in_stock   boolean not null,
  updated_at timestamptz not null default now()
);

create table if not exists hub.price_events (
  id         bigserial primary key,
  book_id    text not null,
  title      text,
  event      text not null check (event in ('new','drop','rise','out_of_stock','back_in_stock')),
  old_price  numeric(8,2),
  new_price  numeric(8,2),
  created_at timestamptz not null default now()
);

create table if not exists hub.dead_letters (
  id          bigserial primary key,
  source      text not null,            -- lead-intake | support-triage-ai
  payload     jsonb not null,
  error       text,
  status      text not null default 'pending' check (status in ('pending','replayed','dropped')),
  attempts    int not null default 0,
  created_at  timestamptz not null default now(),
  replayed_at timestamptz
);

create table if not exists hub.error_log (
  id              bigserial primary key,
  workflow_id     text,
  workflow_name   text,
  execution_id    text,
  failed_node     text,
  message         text,
  mode            text,
  created_at      timestamptz not null default now()
);

create table if not exists hub.health_reports (
  id           bigserial primary key,
  report_date  date not null unique,
  success      int not null,
  failed       int not null,
  by_workflow  jsonb not null default '{}',
  created_at   timestamptz not null default now()
);
-- Not exposed through Supabase PostgREST (only "public" is); lock it down anyway.
alter table hub.leads enable row level security;
alter table hub.tickets enable row level security;
alter table hub.prices enable row level security;
alter table hub.price_events enable row level security;
alter table hub.dead_letters enable row level security;
alter table hub.error_log enable row level security;
alter table hub.health_reports enable row level security;
