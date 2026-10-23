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
    monto              numeric(14, 2) not null check (monto >= 0),
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

-- --------------------------------------------------------------------------- --
-- #35 · Gastos por ítem del presupuesto (F-03 R11 a R16)
-- --------------------------------------------------------------------------- --

-- Un ítem puede valer 0: se listan los ítems y los montos se cargan después (D9).
-- Los gastos siguen exigiendo monto > 0.
alter table public.presupuesto_items drop constraint if exists presupuesto_items_monto_check;
alter table public.presupuesto_items add constraint presupuesto_items_monto_check
    check (monto >= 0);

-- «Imprevistos»: el ítem al que van los gastos que no tienen otro (R12).
-- Como mucho uno vigente por obra.
alter table public.presupuesto_items
    add column if not exists es_imprevistos boolean not null default false;
create unique index if not exists presupuesto_items_un_imprevistos
    on public.presupuesto_items (obra_id) where es_imprevistos and not anulado;

-- Todo gasto pertenece a un ítem (R11). La obra y el rubro del gasto los pone la
-- base a partir del ítem, así nunca quedan inconsistentes.
alter table public.gastos
    add column if not exists presupuesto_item_id bigint references public.presupuesto_items (id);
-- Gastos cargados antes de #35 (sin ítem): van a un ítem vigente de su misma obra
-- y rubro; si no hay, a un ítem nuevo «Gastos anteriores» en 0, así conservan el
-- rubro. Solo toca gastos sin ítem: correrlo de nuevo no cambia nada.
insert into public.presupuesto_items (obra_id, rubro_id, descripcion, monto, moneda)
select distinct g.obra_id, g.rubro_id, 'Gastos anteriores', 0, o.moneda
  from public.gastos g join public.obras o on o.id = g.obra_id
 where g.presupuesto_item_id is null
   and not exists (
        select 1 from public.presupuesto_items i
         where i.obra_id = g.obra_id and i.rubro_id = g.rubro_id and not i.anulado);
update public.gastos g
   set presupuesto_item_id = (
        select min(i.id) from public.presupuesto_items i
         where i.obra_id = g.obra_id and i.rubro_id = g.rubro_id and not i.anulado)
 where g.presupuesto_item_id is null;
alter table public.gastos alter column presupuesto_item_id set not null;
create index if not exists gastos_item_idx on public.gastos (presupuesto_item_id);

create or replace function public.gasto_desde_item()
returns trigger
language plpgsql
set search_path = ''
as $$
declare
    item public.presupuesto_items%rowtype;
begin
    -- FOR SHARE: mientras se inserta el gasto, nadie puede cambiar el rubro del
    -- ítem ni borrarlo; si otro ya lo estaba cambiando, se espera y se lee el
    -- valor confirmado (así el gasto nunca queda con un rubro viejo o bajo un
    -- ítem borrado).
    select * into item from public.presupuesto_items
     where id = new.presupuesto_item_id
       for share;
    if not found then
        raise exception 'El ítem del presupuesto no existe.' using errcode = '23503';
    end if;
    if item.anulado then
        raise exception 'El ítem del presupuesto fue borrado.' using errcode = '23514';
    end if;
    if new.obra_id is not null and new.obra_id <> item.obra_id then
        raise exception 'El ítem es de otra obra.' using errcode = '23514';
    end if;
    -- R7: un rubro desactivado no recibe gastos nuevos ni gastos movidos desde
    -- otro ítem. Los gastos que ya estaban se siguen pudiendo editar sin moverlos.
    if (tg_op = 'INSERT' or new.presupuesto_item_id is distinct from old.presupuesto_item_id)
       and exists (select 1 from public.rubros r where r.id = item.rubro_id and not r.activo) then
        raise exception 'El rubro del ítem está desactivado.' using errcode = '23514';
    end if;
    new.obra_id := item.obra_id;
    new.rubro_id := item.rubro_id;
    return new;
end;
$$;

drop trigger if exists gastos_desde_item on public.gastos;
create trigger gastos_desde_item
    before insert or update of presupuesto_item_id on public.gastos
    for each row execute function public.gasto_desde_item();

-- #25 · Editar un gasto: todos sus datos menos la obra y el autor; también se
-- puede mover a otro ítem vigente de la misma obra (lo valida gasto_desde_item).
-- Queda registro de quién lo editó y cuándo. Un gasto anulado ya no se edita.
alter table public.gastos add column if not exists editado_en timestamptz;
alter table public.gastos add column if not exists editado_por uuid references auth.users (id);

create or replace function public.gasto_editado()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
    if old.anulado then
        raise exception 'Un gasto anulado no se puede editar.' using errcode = '23514';
    end if;
    new.editado_en := now();
    new.editado_por := auth.uid();
    return new;
end;
$$;

drop trigger if exists gastos_editado on public.gastos;
create trigger gastos_editado
    before update of presupuesto_item_id, fecha, descripcion, proveedor, monto, moneda,
                     tipo_cambio, tipo_cambio_origen
    on public.gastos
    for each row execute function public.gasto_editado();

-- Si cambia el rubro de un ítem, sus gastos lo siguen (CA-35). Si se borra
-- (anula) un ítem, se anulan sus gastos (R12b). Corre como dueño de la tabla
-- porque el equipo no puede editar gastos.rubro_id directamente.
create or replace function public.item_propaga_a_gastos()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
    if new.rubro_id is distinct from old.rubro_id then
        update public.gastos set rubro_id = new.rubro_id
         where presupuesto_item_id = new.id;
    end if;
    if new.anulado and not old.anulado then
        update public.gastos set anulado = true
         where presupuesto_item_id = new.id and not anulado;
    end if;
    return new;
end;
$$;
revoke execute on function public.item_propaga_a_gastos() from public, anon, authenticated;

drop trigger if exists presupuesto_items_propaga on public.presupuesto_items;
create trigger presupuesto_items_propaga
    after update of rubro_id, anulado on public.presupuesto_items
    for each row execute function public.item_propaga_a_gastos();

-- Anular es definitivo: un gasto o ítem anulado no vuelve a quedar vigente (así
-- no reaparecen gastos bajo un ítem borrado). No hay función de «restaurar».
create or replace function public.anulado_es_definitivo()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
    if old.anulado and not new.anulado then
        raise exception 'Un registro anulado no se puede volver a activar.' using errcode = '23514';
    end if;
    return new;
end;
$$;

drop trigger if exists gastos_anulado_definitivo on public.gastos;
create trigger gastos_anulado_definitivo
    before update of anulado on public.gastos
    for each row execute function public.anulado_es_definitivo();
drop trigger if exists presupuesto_items_anulado_definitivo on public.presupuesto_items;
create trigger presupuesto_items_anulado_definitivo
    before update of anulado on public.presupuesto_items
    for each row execute function public.anulado_es_definitivo();

-- Las obras que todavía no tienen «Imprevistos» (ni vigente ni borrado) lo
-- reciben: 10 % del presupuesto de la obra (0 si no tiene), en su moneda y en el
-- rubro Otros. Las obras nuevas lo crea la app al darlas de alta.
insert into public.presupuesto_items (obra_id, rubro_id, descripcion, monto, moneda, es_imprevistos)
select o.id,
       (select r.id from public.rubros r
         where public.rubro_clave(r.nombre) = 'otros' limit 1),
       'Imprevistos',
       round(coalesce(o.presupuesto, 0) * 0.10, 2),
       o.moneda,
       true
  from public.obras o
 where not exists (
        select 1 from public.presupuesto_items i
         where i.obra_id = o.id and i.es_imprevistos);
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

-- Qué columnas se pueden modificar después de crear un registro (F-03 R9).
-- La obra, la fecha, el autor y el id nunca cambian, aunque se saltee la app.
revoke update on public.presupuesto_items from authenticated, anon;
grant update (rubro_id, descripcion, monto, moneda, tipo_cambio, tipo_cambio_origen, anulado)
    on public.presupuesto_items to authenticated;
revoke update on public.gastos from authenticated, anon;
grant update (presupuesto_item_id, fecha, descripcion, proveedor, monto, moneda,
              tipo_cambio, tipo_cambio_origen, anulado)
    on public.gastos to authenticated;
-- Sin login no se crean gastos (además de RLS): así ni siquiera corre el trigger.
revoke insert on public.gastos from anon;

-- #49 · Datos de la obra editables desde su Detalle (D4): todos los del alta.
-- El autor, la fecha de creación y el id nunca cambian, aunque se saltee la app.
revoke update on public.obras from authenticated, anon;
grant update (nombre, cliente, direccion, municipio, tipo, estado, avance, responsable,
              fecha_inicio, fecha_fin_estimada, presupuesto, moneda)
    on public.obras to authenticated;
-- El nombre de una obra no puede quedar vacío, ni el presupuesto ser negativo.
alter table public.obras drop constraint if exists obras_nombre_no_vacio;
alter table public.obras add constraint obras_nombre_no_vacio
    check (char_length(btrim(nombre)) > 0) not valid;
alter table public.obras drop constraint if exists obras_presupuesto_no_negativo;
alter table public.obras add constraint obras_presupuesto_no_negativo
    check (presupuesto is null or presupuesto >= 0) not valid;

-- #49 · Pantalla de Rubros: se ordenan y se desactivan; el nombre no se edita.
revoke update on public.rubros from authenticated, anon;
grant update (orden, activo) on public.rubros to authenticated;

-- «Otros» siempre activo: ahí va el ítem «Imprevistos» de cada obra nueva.
create or replace function public.rubro_otros_activo()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if not new.activo and public.rubro_clave(new.nombre) = 'otros' then
    raise exception 'El rubro «Otros» no se puede desactivar: ahí va «Imprevistos».'
      using errcode = '23514';
  end if;
  return new;
end;
$$;
revoke execute on function public.rubro_otros_activo() from public, anon, authenticated;

drop trigger if exists rubros_otros_activo on public.rubros;
create trigger rubros_otros_activo
    before update of activo on public.rubros
    for each row execute function public.rubro_otros_activo();


-- --------------------------------------------------------------------------- --
-- F-06 · Proveedores (#37): lista compartida por el equipo, calificaciones y
-- proveedor de cada gasto. Sin DELETE: «Eliminar» archiva.
-- --------------------------------------------------------------------------- --

create table if not exists public.proveedores (
    id         bigint generated always as identity primary key,
    nombre     text not null check (char_length(btrim(nombre)) between 2 and 120),
    contacto   text check (contacto is null or char_length(contacto) <= 120),
    telefono   text check (telefono is null or telefono ~ '^[0-9+() -]{6,30}$'),
    email      text check (email is null or (char_length(email) <= 120
                                             and email ~ '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$')),
    web        text check (web is null or (char_length(web) <= 300 and web ~ '^https://[^[:space:]]+$')),
    cuit       text check (cuit is null or cuit ~ '^[0-9]{2}-[0-9]{8}-[0-9]$'),
    zona       text check (zona is null or char_length(zona) <= 120),
    notas      text check (notas is null or char_length(notas) <= 1000),
    rubro_ids  bigint[] not null default '{}',
    archivado  boolean not null default false,
    creado_por uuid references auth.users (id) default auth.uid(),
    created_at timestamptz not null default now()
);

-- Un proveedor por nombre, sin importar mayúsculas, tildes ni espacios (misma
-- normalización que los rubros).
create unique index if not exists proveedores_nombre_clave_unico
    on public.proveedores (public.rubro_clave(nombre));

-- Los rubros que atiende tienen que existir (es un arreglo: la FK no alcanza).
create or replace function public.proveedor_rubros_validos()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if exists (select 1 from unnest(new.rubro_ids) as r(id)
              where not exists (select 1 from public.rubros x where x.id = r.id)) then
    raise exception 'Un rubro del proveedor no existe.' using errcode = '23503';
  end if;
  return new;
end;
$$;
revoke execute on function public.proveedor_rubros_validos() from public, anon, authenticated;

drop trigger if exists proveedores_rubros_validos on public.proveedores;
create trigger proveedores_rubros_validos
    before insert or update of rubro_ids on public.proveedores
    for each row execute function public.proveedor_rubros_validos();

alter table public.proveedores enable row level security;

drop policy if exists "proveedores: equipo lee" on public.proveedores;
create policy "proveedores: equipo lee" on public.proveedores
    for select to authenticated using (true);
drop policy if exists "proveedores: equipo crea" on public.proveedores;
create policy "proveedores: equipo crea" on public.proveedores
    for insert to authenticated with check (true);
drop policy if exists "proveedores: equipo edita" on public.proveedores;
create policy "proveedores: equipo edita" on public.proveedores
    for update to authenticated using (true) with check (true);

revoke update on public.proveedores from authenticated, anon;
grant update (nombre, contacto, telefono, email, web, cuit, zona, notas, rubro_ids, archivado)
    on public.proveedores to authenticated;
revoke insert on public.proveedores from anon;

-- Calificaciones: una por socio y proveedor; cada uno edita solo la suya.
create table if not exists public.proveedor_calificaciones (
    id           bigint generated always as identity primary key,
    proveedor_id bigint not null references public.proveedores (id),
    estrellas    smallint not null check (estrellas between 1 and 5),
    comentario   text check (comentario is null or char_length(comentario) <= 500),
    autor        text check (autor is null or char_length(autor) <= 200),
    creado_por   uuid not null references auth.users (id) default auth.uid(),
    created_at   timestamptz not null default now(),
    editado_en   timestamptz
);

create unique index if not exists proveedor_calificaciones_una_por_socio
    on public.proveedor_calificaciones (proveedor_id, creado_por);

create or replace function public.calificacion_editada()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.editado_en := now();
  return new;
end;
$$;
revoke execute on function public.calificacion_editada() from public, anon, authenticated;

drop trigger if exists proveedor_calificaciones_editada on public.proveedor_calificaciones;
create trigger proveedor_calificaciones_editada
    before update on public.proveedor_calificaciones
    for each row execute function public.calificacion_editada();

alter table public.proveedor_calificaciones enable row level security;

drop policy if exists "calificaciones: equipo lee" on public.proveedor_calificaciones;
create policy "calificaciones: equipo lee" on public.proveedor_calificaciones
    for select to authenticated using (true);
drop policy if exists "calificaciones: cada uno crea la suya" on public.proveedor_calificaciones;
create policy "calificaciones: cada uno crea la suya" on public.proveedor_calificaciones
    for insert to authenticated with check (creado_por = (select auth.uid()));
drop policy if exists "calificaciones: cada uno edita la suya" on public.proveedor_calificaciones;
create policy "calificaciones: cada uno edita la suya" on public.proveedor_calificaciones
    for update to authenticated
    using (creado_por = (select auth.uid())) with check (creado_por = (select auth.uid()));

revoke update on public.proveedor_calificaciones from authenticated, anon;
grant update (estrellas, comentario, autor) on public.proveedor_calificaciones to authenticated;
revoke insert on public.proveedor_calificaciones from anon;

-- El proveedor de cada gasto sale de la lista. La columna de texto `proveedor`
-- queda como historial de lo que se escribía antes.
alter table public.gastos add column if not exists proveedor_id bigint
    references public.proveedores (id);
create index if not exists gastos_proveedor_idx on public.gastos (proveedor_id);
grant update (proveedor_id) on public.gastos to authenticated;

-- Un proveedor eliminado (archivado) no se elige en gastos nuevos ni editados;
-- los gastos que ya lo tenían lo conservan.
create or replace function public.gasto_proveedor_vigente()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if new.proveedor_id is not null
     and (tg_op = 'INSERT' or new.proveedor_id is distinct from old.proveedor_id)
     and exists (select 1 from public.proveedores p where p.id = new.proveedor_id and p.archivado) then
    raise exception 'Ese proveedor fue eliminado.' using errcode = '23514';
  end if;
  return new;
end;
$$;
revoke execute on function public.gasto_proveedor_vigente() from public, anon, authenticated;

drop trigger if exists gastos_proveedor_vigente on public.gastos;
create trigger gastos_proveedor_vigente
    before insert or update of proveedor_id on public.gastos
    for each row execute function public.gasto_proveedor_vigente();

-- Migración (#37 D4): un proveedor por cada nombre escrito en los gastos
-- (sin importar mayúsculas, tildes ni espacios) y sus gastos vinculados.
insert into public.proveedores (nombre, creado_por)
select distinct on (public.rubro_clave(g.proveedor)) btrim(g.proveedor), g.creado_por
  from public.gastos g
 where g.proveedor is not null and char_length(btrim(g.proveedor)) between 2 and 120
   and not exists (select 1 from public.proveedores p
                    where public.rubro_clave(p.nombre) = public.rubro_clave(g.proveedor))
 order by public.rubro_clave(g.proveedor), g.created_at;

update public.gastos g
   set proveedor_id = p.id
  from public.proveedores p
 where g.proveedor_id is null
   and g.proveedor is not null
   and public.rubro_clave(p.nombre) = public.rubro_clave(g.proveedor);
