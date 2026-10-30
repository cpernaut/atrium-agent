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
    email      text,
    web        text check (web is null or (char_length(web) <= 300 and web ~ '^https://[^[:space:]]+$')),
    cuit       text check (cuit is null or cuit ~ '^[0-9]{2}-[0-9]{8}-[0-9]$'),
    zona       text check (zona is null or char_length(zona) <= 120),
    notas      text check (notas is null or char_length(notas) <= 1000),
    rubro_ids  bigint[] not null default '{}',
    archivado  boolean not null default false,
    creado_por uuid references auth.users (id) default auth.uid(),
    created_at timestamptz not null default now()
);

-- Mail estricto (como atrium/proveedores.py): sin «?», «&», «#» ni «%», que en el
-- botón Mail (mailto:) podrían sumar destinatarios ocultos.
-- Teléfono con al menos seis dígitos (como atrium/proveedores.py): «++++++» no es
-- un teléfono aunque cumpla el largo.
alter table public.proveedores drop constraint if exists proveedores_telefono_digitos;
alter table public.proveedores add constraint proveedores_telefono_digitos check (
    telefono is null or char_length(regexp_replace(telefono, '[^0-9]', '', 'g')) >= 6);

alter table public.proveedores drop constraint if exists proveedores_email_check;
alter table public.proveedores drop constraint if exists proveedores_email_valido;
alter table public.proveedores add constraint proveedores_email_valido check (
    email is null or (char_length(email) <= 120
                      and email ~ '^[A-Za-z0-9._+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$'));

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

-- Quién lo creó y cuándo los pone la base: nadie puede atribuirle un proveedor a
-- otra persona ni elegir la fecha. (Sin login, como al correr este archivo, se
-- conserva el autor que se mande: lo usa la migración de abajo.)
create or replace function public.proveedor_firmado()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.creado_por := coalesce((select auth.uid()), new.creado_por);
  new.created_at := now();
  return new;
end;
$$;
revoke execute on function public.proveedor_firmado() from public, anon, authenticated;

drop trigger if exists proveedores_firmado on public.proveedores;
create trigger proveedores_firmado
    before insert on public.proveedores
    for each row execute function public.proveedor_firmado();

alter table public.proveedores enable row level security;

drop policy if exists "proveedores: equipo lee" on public.proveedores;
create policy "proveedores: equipo lee" on public.proveedores
    for select to authenticated using (true);
drop policy if exists "proveedores: equipo crea" on public.proveedores;
create policy "proveedores: equipo crea" on public.proveedores
    for insert to authenticated with check (creado_por = (select auth.uid()));
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

-- El autor visible sale del login (el mail del JWT), nunca de lo que mande el
-- cliente: nadie puede atribuirle una calificación a otra persona.
create or replace function public.calificacion_firmada()
returns trigger
language plpgsql
set search_path = ''
as $$
declare
  mail text := nullif(current_setting('request.jwt.claims', true), '')::json ->> 'email';
begin
  if tg_op = 'UPDATE' then
    new.editado_en := now();
    new.autor := old.autor;
    new.created_at := old.created_at;
  else
    new.autor := null;
    new.created_at := now();
    new.editado_en := null;
  end if;
  if mail is not null then
    new.autor := mail;
  end if;
  return new;
end;
$$;
revoke execute on function public.calificacion_firmada() from public, anon, authenticated;

drop trigger if exists proveedor_calificaciones_editada on public.proveedor_calificaciones;
drop function if exists public.calificacion_editada();
drop trigger if exists proveedor_calificaciones_firmada on public.proveedor_calificaciones;
create trigger proveedor_calificaciones_firmada
    before insert or update on public.proveedor_calificaciones
    for each row execute function public.calificacion_firmada();

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

-- Un proveedor eliminado (archivado) no recibe calificaciones nuevas (R1b);
-- quien ya lo había calificado puede seguir editando la suya.
create or replace function public.calificacion_proveedor_vigente()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if exists (select 1 from public.proveedores p where p.id = new.proveedor_id and p.archivado) then
    raise exception 'Ese proveedor fue eliminado: no se puede calificar.' using errcode = '23514';
  end if;
  return new;
end;
$$;
revoke execute on function public.calificacion_proveedor_vigente() from public, anon, authenticated;

drop trigger if exists proveedor_calificaciones_vigente on public.proveedor_calificaciones;
create trigger proveedor_calificaciones_vigente
    before insert on public.proveedor_calificaciones
    for each row execute function public.calificacion_proveedor_vigente();

revoke update on public.proveedor_calificaciones from authenticated, anon;
grant update (estrellas, comentario) on public.proveedor_calificaciones to authenticated;
revoke insert on public.proveedor_calificaciones from anon;

-- El proveedor de cada gasto sale de la lista. La columna de texto `proveedor`
-- queda como historial de lo que se escribía antes.
alter table public.gastos add column if not exists proveedor_id bigint
    references public.proveedores (id);
create index if not exists gastos_proveedor_idx on public.gastos (proveedor_id);
grant update (proveedor_id) on public.gastos to authenticated;

-- Cambiar el proveedor es editar el gasto (#25): queda registrado quién y cuándo,
-- y un gasto anulado no se toca. Se recrea acá porque la columna es de F-06.
drop trigger if exists gastos_editado on public.gastos;
create trigger gastos_editado
    before update of presupuesto_item_id, fecha, descripcion, proveedor, proveedor_id, monto,
                     moneda, tipo_cambio, tipo_cambio_origen
    on public.gastos
    for each row execute function public.gasto_editado();

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

-- Migración (#37 D4): un proveedor por cada nombre escrito en los gastos.
-- Vincular no es editar: durante la migración no corre gastos_editado (así no
-- marca los gastos como editados ni frena en los anulados).
alter table public.gastos disable trigger gastos_editado;
-- Migración (#37 D4): un proveedor por cada nombre escrito en los gastos
-- (sin importar mayúsculas, tildes ni espacios) y sus gastos vinculados.
-- Solo mira gastos que todavía no tienen proveedor de la lista: así, volver a
-- correr este archivo después de renombrar un proveedor no recrea el nombre
-- viejo. Un nombre de una sola letra no puede ser proveedor (mínimo 2): queda
-- como texto en el gasto, que lo conserva hasta que se elija uno de la lista.
insert into public.proveedores (nombre, creado_por)
select distinct on (public.rubro_clave(g.proveedor)) btrim(g.proveedor), g.creado_por
  from public.gastos g
 where g.proveedor_id is null
   and g.proveedor is not null and char_length(btrim(g.proveedor)) between 2 and 120
   and not exists (select 1 from public.proveedores p
                    where public.rubro_clave(p.nombre) = public.rubro_clave(g.proveedor))
 order by public.rubro_clave(g.proveedor), g.created_at;

update public.gastos g
   set proveedor_id = p.id
  from public.proveedores p
 where g.proveedor_id is null
   and g.proveedor is not null
   and not p.archivado
   and public.rubro_clave(p.nombre) = public.rubro_clave(g.proveedor);
alter table public.gastos enable trigger gastos_editado;


-- --------------------------------------------------------------------------- --
-- #53 · Texto limpio: lo que se guarda no lleva caracteres de control ni
-- invisibles (ancho cero, cambio de dirección, BOM), ni controles C0, DEL y C1
-- (U+0080–U+009F) como atrium/sanidad.py, ni los marcadores [[ ]] con
-- los que la app le entrega datos al agente. La app además rechaza textos que
-- parecen órdenes para el agente (atrium/sanidad.py).
-- --------------------------------------------------------------------------- --

-- Igual que sanidad.limpiar(): tabulación -> espacio, CR -> salto de línea, ancho
-- completo -> ASCII, y fuera
-- los controles (C0 salvo el salto de línea, DEL, C1) y los caracteres de formato,
-- uso privado y separadores de línea/párrafo (categorías Unicode Cf, Co, Zl, Zp;
-- rangos generados con unicodedata de Python).
create or replace function public.limpiar_texto(t text)
returns text
language sql
immutable
parallel safe
set search_path = ''
as $$
    -- Primero CR/tab, ancho completo y caracteres prohibidos; después los espacios
    -- como sanidad.limpiar: cada tramo (también los Unicode) es uno solo, sin
    -- espacios al borde de las líneas, a lo sumo una línea en blanco seguida y nada
    -- al principio o al final; por último los marcadores.
    select replace(replace(
        pg_catalog.btrim(
            pg_catalog.regexp_replace(
                pg_catalog.regexp_replace(
                    pg_catalog.regexp_replace(
                        pg_catalog.regexp_replace(
                            pg_catalog.translate(
                                replace(replace(replace(t, E'\r\n', E'\n'), E'\r', E'\n'), E'\t', ' '),
                                -- Ancho completo («ｉｇｎｏｒá», «［［») -> ASCII, como sanidad.limpiar.
                                U&'\FF01\FF02\FF03\FF04\FF05\FF06\FF07\FF08\FF09\FF0A\FF0B\FF0C\FF0D\FF0E\FF0F\FF10\FF11\FF12\FF13\FF14\FF15\FF16\FF17\FF18\FF19\FF1A\FF1B\FF1C\FF1D\FF1E\FF1F\FF20\FF21\FF22\FF23\FF24\FF25\FF26\FF27\FF28\FF29\FF2A\FF2B\FF2C\FF2D\FF2E\FF2F\FF30\FF31\FF32\FF33\FF34\FF35\FF36\FF37\FF38\FF39\FF3A\FF3B\FF3C\FF3D\FF3E\FF3F\FF40\FF41\FF42\FF43\FF44\FF45\FF46\FF47\FF48\FF49\FF4A\FF4B\FF4C\FF4D\FF4E\FF4F\FF50\FF51\FF52\FF53\FF54\FF55\FF56\FF57\FF58\FF59\FF5A\FF5B\FF5C\FF5D\FF5E\3000',
                                U&'\0021\0022\0023\0024\0025\0026\0027\0028\0029\002A\002B\002C\002D\002E\002F\0030\0031\0032\0033\0034\0035\0036\0037\0038\0039\003A\003B\003C\003D\003E\003F\0040\0041\0042\0043\0044\0045\0046\0047\0048\0049\004A\004B\004C\004D\004E\004F\0050\0051\0052\0053\0054\0055\0056\0057\0058\0059\005A\005B\005C\005D\005E\005F\0060\0061\0062\0063\0064\0065\0066\0067\0068\0069\006A\006B\006C\006D\006E\006F\0070\0071\0072\0073\0074\0075\0076\0077\0078\0079\007A\007B\007C\007D\007E\0020'),
                            '[\x01-\x08\x0B\x0C\x0E-\x1F\x7F-\x9F\u00AD\u0600-\u0605\u061C\u06DD\u070F\u0890-\u0891\u08E2\u180E\u200B-\u200F\u2028-\u202E\u2060-\u2064\u2066-\u206F\uE000-\uF8FF\uFEFF\uFFF9-\uFFFB\U000110BD\U000110CD\U00013430-\U0001343F\U0001BCA0-\U0001BCA3\U0001D173-\U0001D17A\U000E0001\U000E0020-\U000E007F\U000F0000-\U000FFFFD\U00100000-\U0010FFFD]',
                            '', 'g'),
                        '[ \u00A0\u1680\u2000-\u200A\u202F\u205F]+', ' ', 'g'),
                    ' ?\n ?', E'\n', 'g'),
                '\n{3,}', E'\n\n', 'g'),
            E' \n'),
        '[[', '[ ['), ']]', '] ]')
$$;
revoke execute on function public.limpiar_texto(text) from public, anon;
grant execute on function public.limpiar_texto(text) to authenticated, service_role;

create or replace function public.texto_limpio(t text)
returns boolean
language sql
immutable
parallel safe
set search_path = ''
as $$
    select t is null or t = public.limpiar_texto(t)
$$;
revoke execute on function public.texto_limpio(text) from public, anon;
grant execute on function public.texto_limpio(text) to authenticated, service_role;

-- Campos de una línea (nombres, descripciones, contacto…): como sanidad.limpiar sin
-- multilinea, los saltos de línea también pasan a ser un espacio. Los textos largos
-- (nota, notas, comentario) usan limpiar_texto / texto_limpio y conservan sus líneas.
create or replace function public.limpiar_linea(t text)
returns text
language sql
immutable
parallel safe
set search_path = ''
as $$
    select pg_catalog.btrim(
        pg_catalog.regexp_replace(public.limpiar_texto(t), '[ \n]+', ' ', 'g'))
$$;
revoke execute on function public.limpiar_linea(text) from public, anon;
grant execute on function public.limpiar_linea(text) to authenticated, service_role;

create or replace function public.linea_limpia(t text)
returns boolean
language sql
immutable
parallel safe
set search_path = ''
as $$
    select t is null or t = public.limpiar_linea(t)
$$;
revoke execute on function public.linea_limpia(text) from public, anon;
grant execute on function public.linea_limpia(text) to authenticated, service_role;

-- Datos ya guardados (#53 D2): se limpian solos. No es una edición de nadie: los
-- triggers que registran ediciones no corren mientras tanto.
alter table public.gastos disable trigger gastos_editado;
alter table public.proveedor_calificaciones disable trigger proveedor_calificaciones_firmada;
-- Un texto obligatorio que queda vacío al limpiarse (solo tenía invisibles) toma un
-- reemplazo («Sin nombre», «Sin descripción», «(sin texto)»); uno opcional, null.
update public.obras
   set nombre = coalesce(nullif(btrim(public.limpiar_linea(nombre)), ''), 'Sin nombre')
 where not public.linea_limpia(nombre);
update public.obras set cliente = nullif(btrim(public.limpiar_linea(cliente)), '')
 where not public.linea_limpia(cliente);
update public.obras set direccion = nullif(btrim(public.limpiar_linea(direccion)), '')
 where not public.linea_limpia(direccion);
update public.obras set responsable = nullif(btrim(public.limpiar_linea(responsable)), '')
 where not public.linea_limpia(responsable);
update public.bitacora set autor = nullif(public.limpiar_linea(autor), '')
 where not public.linea_limpia(autor);
update public.bitacora
   set nota = coalesce(nullif(btrim(public.limpiar_texto(nota)), ''), '(sin texto)')
 where not public.texto_limpio(nota);
update public.presupuesto_items
   set descripcion = nullif(btrim(public.limpiar_linea(descripcion)), '')
 where not public.linea_limpia(descripcion);
update public.gastos
   set descripcion = coalesce(nullif(btrim(public.limpiar_linea(descripcion)), ''), 'Sin descripción')
 where not public.linea_limpia(descripcion);
update public.gastos set proveedor = nullif(btrim(public.limpiar_linea(proveedor)), '')
 where not public.linea_limpia(proveedor);
-- Rubros y proveedores tienen nombre único (rubro_clave) y un largo mínimo. Fila
-- por fila, cada nombre sucio toma su versión limpia; si queda vacío o corto pasa a
-- «Sin nombre», y si coincide con otro (por ejemplo «Acme» y «Acme» con un
-- invisible) se le suma un número libre: «Acme (2)», «Acme (3)»… Nada se fusiona
-- ni se pierde: cada uno conserva sus gastos, ítems y calificaciones.
do $$
declare
    t record;
    fila record;
    base text;
    candidato text;
    n int;
    ocupado boolean;
begin
    for t in select * from (values ('rubros', 60), ('proveedores', 120)) as x(tabla, largo) loop
        for fila in execute format(
            'select id, nombre from public.%I where not public.linea_limpia(nombre) order by id',
            t.tabla)
        loop
            base := btrim(public.limpiar_linea(fila.nombre));
            if char_length(base) < 2 then
                base := 'Sin nombre';
            end if;
            candidato := left(base, t.largo);
            n := 1;
            loop
                execute format(
                    'select exists (select 1 from public.%I where id <> $1 '
                    'and public.rubro_clave(nombre) = public.rubro_clave($2))', t.tabla)
                    into ocupado using fila.id, candidato;
                exit when not ocupado;
                n := n + 1;
                candidato := left(base, t.largo - char_length(' (' || n || ')')) || ' (' || n || ')';
            end loop;
            execute format('update public.%I set nombre = $1 where id = $2', t.tabla)
                using candidato, fila.id;
        end loop;
    end loop;
end
$$;
update public.proveedores set contacto = nullif(btrim(public.limpiar_linea(contacto)), '')
 where not public.linea_limpia(contacto);
update public.proveedores set zona = nullif(btrim(public.limpiar_linea(zona)), '')
 where not public.linea_limpia(zona);
update public.proveedores set web = nullif(btrim(public.limpiar_linea(web)), '')
 where not public.linea_limpia(web);
update public.proveedores set notas = nullif(btrim(public.limpiar_texto(notas)), '')
 where not public.texto_limpio(notas);
update public.proveedor_calificaciones
   set comentario = nullif(btrim(public.limpiar_texto(comentario)), '')
 where not public.texto_limpio(comentario);
alter table public.gastos enable trigger gastos_editado;
alter table public.proveedor_calificaciones enable trigger proveedor_calificaciones_firmada;

-- El autor de una nota de bitácora sale del login (el mail del JWT), como en las
-- calificaciones: nadie firma una nota con otro nombre ni con texto propio.
create or replace function public.bitacora_firmada()
returns trigger
language plpgsql
set search_path = ''
as $$
declare
  claims json := nullif(current_setting('request.jwt.claims', true), '')::json;
begin
  -- Sin JWT (el propio esquema, una migración) se respeta lo que viene. Con login,
  -- el autor es siempre su mail; un login sin mail no puede anotar.
  if claims is not null and claims ->> 'role' is distinct from 'service_role' then
    if nullif(claims ->> 'email', '') is null then
      raise exception 'Para anotar en la bitácora hace falta un usuario con mail.'
        using errcode = '42501';
    end if;
    new.autor := claims ->> 'email';
  end if;
  return new;
end;
$$;
revoke execute on function public.bitacora_firmada() from public, anon, authenticated;
drop trigger if exists bitacora_firmada on public.bitacora;
create trigger bitacora_firmada
    before insert on public.bitacora
    for each row execute function public.bitacora_firmada();

-- Y de acá en más la base no acepta texto sucio, aunque se saltee la app.
alter table public.obras drop constraint if exists obras_textos_limpios;
alter table public.obras add constraint obras_textos_limpios check (
    public.linea_limpia(nombre) and public.linea_limpia(cliente)
    and public.linea_limpia(direccion) and public.linea_limpia(responsable));
alter table public.bitacora drop constraint if exists bitacora_texto_limpio;
alter table public.bitacora add constraint bitacora_texto_limpio
    check (public.texto_limpio(nota) and public.linea_limpia(autor));
alter table public.presupuesto_items drop constraint if exists presupuesto_texto_limpio;
alter table public.presupuesto_items add constraint presupuesto_texto_limpio
    check (public.linea_limpia(descripcion));
alter table public.gastos drop constraint if exists gastos_textos_limpios;
alter table public.gastos add constraint gastos_textos_limpios
    check (public.linea_limpia(descripcion) and public.linea_limpia(proveedor));
alter table public.rubros drop constraint if exists rubros_texto_limpio;
alter table public.rubros add constraint rubros_texto_limpio check (public.linea_limpia(nombre));
alter table public.proveedores drop constraint if exists proveedores_textos_limpios;
alter table public.proveedores add constraint proveedores_textos_limpios check (
    public.linea_limpia(nombre) and public.linea_limpia(contacto)
    and public.linea_limpia(zona) and public.texto_limpio(notas) and public.linea_limpia(web));
alter table public.proveedor_calificaciones drop constraint if exists calificaciones_texto_limpio;
alter table public.proveedor_calificaciones add constraint calificaciones_texto_limpio
    check (public.texto_limpio(comentario));

-- --------------------------------------------------------------------------- --
-- #55 · Ítems por unidad de medida. Un ítem es «Global» (un monto total, como
-- siempre) o por unidad: cantidad × precio unitario = monto. Los ítems que ya
-- existían quedan «Global» con su monto (D22). Todo lo que suma por monto
-- (semáforo, desvíos, resumen) no cambia.
-- --------------------------------------------------------------------------- --
alter table public.presupuesto_items
    add column if not exists unidad text not null default 'global';
alter table public.presupuesto_items
    add column if not exists cantidad numeric(12, 2);
alter table public.presupuesto_items
    add column if not exists precio_unitario numeric(14, 2);

alter table public.presupuesto_items drop constraint if exists presupuesto_items_unidad;
alter table public.presupuesto_items add constraint presupuesto_items_unidad check (
    unidad in ('global', 'm2', 'm3', 'ml', 'kg', 'unidad', 'caja', 'jornal'));
-- «Global»: sin cantidad ni precio. Por unidad: los dos (pueden valer 0, D23) y el
-- monto es exactamente cantidad × precio, redondeado a centavos.
alter table public.presupuesto_items drop constraint if exists presupuesto_items_por_unidad;
alter table public.presupuesto_items add constraint presupuesto_items_por_unidad check (
    (unidad = 'global' and cantidad is null and precio_unitario is null)
    or (unidad <> 'global' and cantidad is not null and precio_unitario is not null
        and cantidad >= 0 and precio_unitario >= 0
        and monto = round(cantidad * precio_unitario, 2)));
-- «Imprevistos» es siempre global (D25).
alter table public.presupuesto_items drop constraint if exists presupuesto_items_imprevistos_global;
alter table public.presupuesto_items add constraint presupuesto_items_imprevistos_global
    check (not es_imprevistos or unidad = 'global');

grant update (unidad, cantidad, precio_unitario) on public.presupuesto_items to authenticated;
