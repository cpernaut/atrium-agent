-- Run in the Supabase SQL Editor (SQL Editor → New query → Run).
-- Tables + row-level security used by app.py (chat history, obras tracker and
-- presupuesto y gastos).
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


-- --------------------------------------------------------------------------- --
-- F-03 · Presupuesto y gastos (tablas `rubros`, `presupuesto_items`, `gastos`).
-- Compartidas por el equipo. Sin DELETE: los gastos e ítems se anulan y los
-- rubros se desactivan. Las reglas de datos se validan también acá, no solo en
-- la app.
-- --------------------------------------------------------------------------- --

create table if not exists public.rubros (
    id         bigint generated always as identity primary key,
    nombre     text not null check (char_length(btrim(nombre)) between 2 and 60),
    orden      int  not null default 1000 check (orden >= 0),
    activo     boolean not null default true,
    creado_por uuid references auth.users (id) default auth.uid(),
    created_at timestamptz not null default now()
);

-- Un rubro por nombre, sin importar mayúsculas, tildes ni espacios de más
-- («Mampostería» = «mamposteria» = «MAMPOSTERÍA  »). Misma regla que
-- finanzas.normalizar en la app, pero acá vale también ante cargas simultáneas.
create or replace function public.rubro_clave(nombre text)
returns text
language sql
immutable
parallel safe
set search_path = ''
as $$
    select pg_catalog.translate(
        pg_catalog.regexp_replace(pg_catalog.lower(pg_catalog.btrim(nombre)), '\s+', ' ', 'g'),
        'áàäâãåéèëêíìïîóòöôõúùüûýÿçñ',
        'aaaaaaeeeeiiiiooooouuuuyycn'
    )
$$;
revoke execute on function public.rubro_clave(text) from public, anon;
grant execute on function public.rubro_clave(text) to authenticated, service_role;

drop index if exists public.rubros_nombre_unico;
create unique index if not exists rubros_nombre_clave_unico
    on public.rubros (public.rubro_clave(nombre));

-- Precarga. Si un rubro ya existe (con cualquier mayúscula) no se duplica.
insert into public.rubros (nombre, orden) values
    ('Trabajos preliminares', 10),
    ('Movimiento de suelo', 20),
    ('Fundaciones', 30),
    ('Estructura', 40),
    ('Steel frame', 50),
    ('Mampostería', 60),
    ('Cubierta', 70),
    ('Instalación sanitaria', 80),
    ('Instalación eléctrica', 90),
    ('Instalación de gas', 100),
    ('Revoques', 110),
    ('Contrapisos y carpetas', 120),
    ('Pisos y revestimientos', 130),
    ('Carpinterías', 140),
    ('Pintura', 150),
    ('Honorarios y trámites', 160),
    ('Limpieza final', 170),
    ('Otros', 999)
on conflict do nothing;

create table if not exists public.presupuesto_items (
    id                 bigint generated always as identity primary key,
    obra_id            bigint not null references public.obras (id) on delete cascade,
    rubro_id           bigint not null references public.rubros (id),
    descripcion        text check (descripcion is null or char_length(descripcion) <= 200),
    monto              numeric(14, 2) not null check (monto > 0),
    moneda             text not null check (moneda in ('ARS', 'USD')),
    fecha              date not null default current_date,
    tipo_cambio        numeric(12, 4) check (tipo_cambio is null or tipo_cambio > 0),
    tipo_cambio_origen text check (tipo_cambio_origen in ('auto', 'manual')),
    anulado            boolean not null default false,
    creado_por         uuid references auth.users (id) default auth.uid(),
    created_at         timestamptz not null default now(),
    constraint presupuesto_tc_con_origen
        check ((tipo_cambio is null) = (tipo_cambio_origen is null))
);

create table if not exists public.gastos (
    id                 bigint generated always as identity primary key,
    obra_id            bigint not null references public.obras (id) on delete cascade,
    fecha              date not null,
    rubro_id           bigint not null references public.rubros (id),
    descripcion        text not null
                       check (char_length(btrim(descripcion)) between 1 and 200),
    proveedor          text check (proveedor is null or char_length(proveedor) <= 120),
    monto              numeric(14, 2) not null check (monto > 0),
    moneda             text not null check (moneda in ('ARS', 'USD')),
    tipo_cambio        numeric(12, 4) check (tipo_cambio is null or tipo_cambio > 0),
    tipo_cambio_origen text check (tipo_cambio_origen in ('auto', 'manual')),
    anulado            boolean not null default false,
    creado_por         uuid references auth.users (id) default auth.uid(),
    created_at         timestamptz not null default now(),
    constraint gastos_tc_con_origen
        check ((tipo_cambio is null) = (tipo_cambio_origen is null))
);

-- Fechas en hora argentina: la base corre en UTC y, entre las 21:00 y las 24:00,
-- current_date ya sería «mañana». Como alter, para que valga también en tablas
-- que ya existían cuando se vuelve a correr este archivo.
alter table public.gastos
    alter column fecha set default (now() at time zone 'America/Argentina/Buenos_Aires')::date;
alter table public.gastos drop constraint if exists gastos_fecha_check;
alter table public.gastos drop constraint if exists gastos_fecha_no_futura;
alter table public.gastos add constraint gastos_fecha_no_futura
    check (fecha <= (now() at time zone 'America/Argentina/Buenos_Aires')::date);
alter table public.presupuesto_items
    alter column fecha set default (now() at time zone 'America/Argentina/Buenos_Aires')::date;
alter table public.bitacora
    alter column fecha set default (now() at time zone 'America/Argentina/Buenos_Aires')::date;

create index if not exists presupuesto_items_obra_idx on public.presupuesto_items (obra_id);
create index if not exists gastos_obra_fecha_idx on public.gastos (obra_id, fecha desc);

alter table public.rubros            enable row level security;
alter table public.presupuesto_items enable row level security;
alter table public.gastos            enable row level security;

drop policy if exists "rubros: equipo lee" on public.rubros;
create policy "rubros: equipo lee" on public.rubros
    for select to authenticated using (true);

drop policy if exists "rubros: equipo crea" on public.rubros;
create policy "rubros: equipo crea" on public.rubros
    for insert to authenticated with check (true);

drop policy if exists "rubros: equipo edita" on public.rubros;
create policy "rubros: equipo edita" on public.rubros
    for update to authenticated using (true) with check (true);

drop policy if exists "presupuesto: equipo lee" on public.presupuesto_items;
create policy "presupuesto: equipo lee" on public.presupuesto_items
    for select to authenticated using (true);

drop policy if exists "presupuesto: equipo crea" on public.presupuesto_items;
create policy "presupuesto: equipo crea" on public.presupuesto_items
    for insert to authenticated with check (true);

drop policy if exists "presupuesto: equipo edita" on public.presupuesto_items;
create policy "presupuesto: equipo edita" on public.presupuesto_items
    for update to authenticated using (true) with check (true);

drop policy if exists "gastos: equipo lee" on public.gastos;
create policy "gastos: equipo lee" on public.gastos
    for select to authenticated using (true);

drop policy if exists "gastos: equipo crea" on public.gastos;
create policy "gastos: equipo crea" on public.gastos
    for insert to authenticated with check (true);

drop policy if exists "gastos: equipo edita" on public.gastos;
create policy "gastos: equipo edita" on public.gastos
    for update to authenticated using (true) with check (true);
