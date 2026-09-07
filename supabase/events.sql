create table if not exists public.events (
  id text primary key,
  node_id text not null,
  node_name text not null,
  lat double precision not null,
  lng double precision not null,
  recorded_at timestamptz not null,
  source text not null check (source in ('esp32_node', 'phone_layer')),
  confirmation text not null,
  classification text not null check (classification in ('normal', 'event')),
  confidence double precision not null check (confidence >= 0 and confidence <= 1),
  features jsonb not null,
  telemetry jsonb not null,
  created_at timestamptz not null default now()
);

create index if not exists events_recorded_at_idx on public.events (recorded_at desc);
create index if not exists events_node_id_idx on public.events (node_id);

alter table public.events enable row level security;
