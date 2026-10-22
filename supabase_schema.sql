-- Run in the Supabase SQL Editor (SQL Editor → New query → Run).
-- Tables + row-level security used by app.py (chat history and obras tracker).
-- Safe to re-run: every statement is idempotent.

create table if not exists public.mensajes (
    id         bigint generated always as identity primary key,
    user_id    uuid not null references auth.users (id) default auth.uid(),
    thread_id  text not null,
    rol        text not null check (rol in ('user', 'assistant')),
    contenido  text not null,
    created_at timestamptz not null default now()
);

create index if not exists mensajes_user_created_idx
    on public.mensajes (user_id, created_at);

alter table public.mensajes enable row level security;

drop policy if exists "mensajes: select own" on public.mensajes;
create policy "mensajes: select own" on public.mensajes
    for select using (auth.uid() = user_id);

drop policy if exists "mensajes: insert own" on public.mensajes;
create policy "mensajes: insert own" on public.mensajes
    for insert with check (auth.uid() = user_id);


-- --------------------------------------------------------------------------- --
-- Tracker de obras (tablas `obras` + `bitacora`).
-- Compartidas por todo el equipo: cualquier usuario logueado lee y escribe.
-- Importante: en Authentication → Sign In / Providers, desactivar
-- "Allow new users to sign up" para que solo entren los usuarios que crees vos.
-- --------------------------------------------------------------------------- --

create table if not exists public.obras (
    id                 bigint generated always as identity primary key,
    nombre             text not null,
    cliente            text,
    direccion          text,
    municipio          text,
    tipo               text,
    estado             text not null default 'Planificación',
    responsable        text,
    fecha_inicio       date,
    fecha_fin_estimada date,
    presupuesto        numeric(14, 2),
    moneda             text not null default 'ARS' check (moneda in ('ARS', 'USD')),
    avance             int  not null default 0 check (avance between 0 and 100),
    creado_por         uuid references auth.users (id) default auth.uid(),
    created_at         timestamptz not null default now()
);

create table if not exists public.bitacora (
    id         bigint generated always as identity primary key,
    obra_id    bigint not null references public.obras (id) on delete cascade,
    fecha      date not null default current_date,
    autor      text,
    nota       text not null,
    creado_por uuid references auth.users (id) default auth.uid(),
    created_at timestamptz not null default now()
);

create index if not exists bitacora_obra_fecha_idx
    on public.bitacora (obra_id, fecha desc);

alter table public.obras    enable row level security;
alter table public.bitacora enable row level security;

drop policy if exists "obras: equipo lee" on public.obras;
create policy "obras: equipo lee" on public.obras
    for select to authenticated using (true);

drop policy if exists "obras: equipo crea" on public.obras;
create policy "obras: equipo crea" on public.obras
    for insert to authenticated with check (true);

drop policy if exists "obras: equipo edita" on public.obras;
create policy "obras: equipo edita" on public.obras
    for update to authenticated using (true) with check (true);

drop policy if exists "bitacora: equipo lee" on public.bitacora;
create policy "bitacora: equipo lee" on public.bitacora
    for select to authenticated using (true);

drop policy if exists "bitacora: equipo crea" on public.bitacora;
create policy "bitacora: equipo crea" on public.bitacora
    for insert to authenticated with check (true);
