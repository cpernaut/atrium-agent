-- Security and integrity checks for F-03 on a real Postgres.
-- Every check raises on failure; run with ON_ERROR_STOP.
\set ON_ERROR_STOP 1

create function pg_temp.como(rol text, uid text) returns void language plpgsql as $$
begin
  perform set_config('request.jwt.claims',
    case when uid is null then '{"role":"anon"}'
         else json_build_object('sub', uid, 'role', rol,
                                'email', right(uid, 1) || '@atrium.test')::text end, false);
  execute format('set role %I', rol);
end $$;

create function pg_temp.falla(sql text, esperado text) returns void language plpgsql as $$
begin
  begin
    execute sql;
  exception when others then
    if sqlstate = esperado then return; end if;
    raise exception 'FALLÓ: «%» dio % (%), se esperaba %', sql, sqlstate, sqlerrm, esperado;
  end;
  raise exception 'FALLÓ: «%» se ejecutó y tenía que ser rechazado (%)', sql, esperado;
end $$;

create function pg_temp.ok(condicion boolean, que text) returns void language plpgsql as $$
begin
  if not condicion then raise exception 'FALLÓ: %', que; end if;
  raise notice 'OK  %', que;
end $$;

-- ----- precarga -----
select pg_temp.ok((select count(*) from public.rubros where nombre not like 'Acme%' and nombre not like 'Sin nombre%') = 18,
                  'precarga: 18 rubros (además de los «Acme» de la migración #53)');
select pg_temp.ok(exists(select 1 from public.rubros where nombre = 'Steel frame' and orden = 50),
                  'precarga: Steel frame');

-- ----- migración #35: «Imprevistos» en obras que ya existían -----
select pg_temp.ok(
  (select count(*) = 1 and bool_and(i.monto = 5000 and i.moneda = 'USD' and i.descripcion = 'Imprevistos'
          and r.nombre = 'Otros' and not i.anulado)
     from public.presupuesto_items i join public.obras o on o.id = i.obra_id
     join public.rubros r on r.id = i.rubro_id
    where o.nombre = 'Obra previa' and i.es_imprevistos),
  'migración: «Imprevistos» = 10 % del presupuesto, en la moneda de la obra y en Otros, una sola vez');
select pg_temp.ok(
  (select i.monto = 0 and i.moneda = 'ARS' from public.presupuesto_items i join public.obras o on o.id = i.obra_id
    where o.nombre = 'Obra previa sin presupuesto' and i.es_imprevistos),
  'migración: obra sin presupuesto -> «Imprevistos» en 0');

select pg_temp.ok(
  (select count(*) = 5 and bool_and(g.presupuesto_item_id is not null and i.obra_id = g.obra_id
                                    and i.rubro_id = g.rubro_id)
     from public.gastos g join public.presupuesto_items i on i.id = g.presupuesto_item_id
    where g.descripcion like 'Gasto previo%'),
  'migración: los gastos anteriores quedan en un ítem de su obra y rubro');
select pg_temp.ok(
  (select i.descripcion = 'Hierro previo' from public.gastos g
     join public.presupuesto_items i on i.id = g.presupuesto_item_id
    where g.descripcion = 'Gasto previo con ítem')
  and (select count(distinct g.presupuesto_item_id) = 1 and bool_and(i.descripcion = 'Gastos anteriores'
                                                          and i.monto = 0 and not i.es_imprevistos)
         from public.gastos g join public.presupuesto_items i on i.id = g.presupuesto_item_id
        where g.descripcion in ('Gasto previo sin ítem', 'Gasto previo anulado'))
  and (select anulado from public.gastos where descripcion = 'Gasto previo anulado'),
  'migración: usa el ítem del mismo rubro o crea «Gastos anteriores» en 0; respeta anulados');

-- ----- migración #37: proveedores escritos a mano -> lista de proveedores -----
select pg_temp.ok(
  (select count(*) from public.proveedores where nombre not like 'Pinturas Z%') = 2
  and exists (select 1 from public.proveedores where nombre = 'Hierros del Sur')
  and not exists (select 1 from public.proveedores where public.rubro_clave(nombre) = 'hierros sur')
  and (select proveedor = 'Y' and proveedor_id is null from public.gastos
        where descripcion = 'Gasto previo de una letra')
  and (select count(*) from public.gastos where proveedor is not null and proveedor_id is null) = 1
  and not exists (select 1 from public.gastos where descripcion like 'Gasto previo%' and editado_en is not null)
  and (select count(distinct proveedor_id) from public.gastos
        where descripcion in ('Gasto previo con ítem', 'Gasto previo sin ítem')) = 1
  and (select p.nombre from public.gastos g join public.proveedores p on p.id = g.proveedor_id
        where g.descripcion = 'Gasto previo anulado') = 'Pinturería X',
  'migración #37: un proveedor por nombre y sus gastos vinculados; renombrar y volver a correr no lo recrea; una letra queda como texto');

-- ----- #53: texto limpio -----
select pg_temp.ok(
  exists (select 1 from public.gastos where descripcion = 'Gasto previo con invisibles y [ [marcas] ]')
  and not exists (select 1 from public.gastos where not public.texto_limpio(descripcion)),
  'texto limpio #53: los datos ya guardados se limpian solos (invisibles y marcadores)');
select pg_temp.ok(
  exists (select 1 from public.obras where nombre = 'Sin nombre' and cliente is null)
  and exists (select 1 from public.gastos where descripcion = 'Sin descripción' and monto = 5),
  'texto limpio #53: un texto que queda vacío al limpiarse toma un reemplazo (obligatorio) o queda vacío (opcional)');
select pg_temp.ok(
  (select count(*) from public.proveedores where nombre in ('Pinturas Z')
      or nombre ~ '^Pinturas Z \([0-9]+\)$') = 2
  and (select count(distinct g.proveedor_id) from public.gastos g
        where g.descripcion like 'Gasto de Pinturas Z%') = 2
  and (select count(*) from public.rubros where nombre = 'Acme' or nombre ~ '^Acme \([0-9]+\)$') = 4
  and (select count(*) from public.rubros where nombre ~ '^Sin nombre( \([0-9]+\))?$') = 2
  and not exists (select 1 from public.rubros where not public.texto_limpio(nombre))
  and not exists (select 1 from public.proveedores where not public.texto_limpio(nombre)),
  'texto limpio #53: nombres que al limpiarse coinciden o quedan vacíos no chocan: número libre o «Sin nombre», cada uno con sus datos');

-- ----- usuario A logueado -----
select pg_temp.como('authenticated', '00000000-0000-0000-0000-00000000000a');
insert into public.obras (nombre) values ('Obra RLS'), ('Obra ajena');
select pg_temp.ok((select creado_por from public.obras where nombre = 'Obra RLS')
                  = '00000000-0000-0000-0000-00000000000a', 'obra firmada por su autor');

insert into public.presupuesto_items (obra_id, rubro_id, descripcion, monto, moneda, tipo_cambio, tipo_cambio_origen)
  select o.id, r.id, 'Hierro', 1000, 'ARS', 1200, 'auto' from public.obras o, public.rubros r
  where o.nombre = 'Obra RLS' and r.nombre = 'Estructura';
create temp view item_hierro as
  select * from public.presupuesto_items where descripcion = 'Hierro';
grant select on item_hierro to authenticated, anon;
-- Obra y rubro los pone la base desde el ítem (R11): aunque se manden otros.
insert into public.gastos (presupuesto_item_id, rubro_id, descripcion, monto, moneda)
  select id, (select id from public.rubros where nombre = 'Pintura'), 'Hierro', 350000, 'ARS'
  from item_hierro;
select pg_temp.ok((select g.fecha = (now() at time zone 'America/Argentina/Buenos_Aires')::date
                          and not g.anulado and g.tipo_cambio is null
                          and g.obra_id = i.obra_id and g.rubro_id = i.rubro_id
                   from public.gastos g join item_hierro i on i.id = g.presupuesto_item_id
                   where g.descripcion = 'Hierro'),
                  'gasto: defaults y obra/rubro tomados del ítem');
-- «Mañana» en Argentina se rechaza siempre, también entre las 21 y las 24 (UTC ya es mañana).
select pg_temp.falla($$insert into public.gastos (presupuesto_item_id, descripcion, monto, moneda, fecha)
  select id, 'x', 10, 'ARS', (now() at time zone 'America/Argentina/Buenos_Aires')::date + 1
  from item_hierro$$, '23514');
select pg_temp.ok(
  (select pg_get_constraintdef(oid) like '%America/Argentina/Buenos_Aires%'
   from pg_constraint where conname = 'gastos_fecha_no_futura')
  and (select bool_and(pg_get_expr(d.adbin, d.adrelid) like '%America/Argentina/Buenos_Aires%')
       from pg_attrdef d join pg_attribute a on a.attrelid = d.adrelid and a.attnum = d.adnum
       where a.attname = 'fecha'
         and d.adrelid in ('public.gastos'::regclass, 'public.presupuesto_items'::regclass,
                           'public.bitacora'::regclass)),
  'fechas: default y validación en hora argentina (gastos, presupuesto, bitácora)');

-- Integridad (F-03-CA-10): la base rechaza datos inválidos aunque se saltee la app.
select pg_temp.falla($$insert into public.gastos (presupuesto_item_id, descripcion, monto, moneda)
  select id, 'x', 0, 'ARS' from item_hierro$$, '23514');
select pg_temp.falla($$insert into public.gastos (presupuesto_item_id, descripcion, monto, moneda)
  select id, 'x', -5, 'ARS' from item_hierro$$, '23514');
select pg_temp.falla($$insert into public.gastos (presupuesto_item_id, descripcion, monto, moneda)
  select id, '   ', 10, 'ARS' from item_hierro$$, '23514');
select pg_temp.falla($$insert into public.gastos (presupuesto_item_id, descripcion, monto, moneda)
  select id, null, 10, 'ARS' from item_hierro$$, '23502');
select pg_temp.falla($$insert into public.gastos (presupuesto_item_id, descripcion, monto, moneda)
  select id, 'x', 10, 'EUR' from item_hierro$$, '23514');
select pg_temp.falla($$insert into public.gastos (presupuesto_item_id, descripcion, monto, moneda, fecha)
  select id, 'x', 10, 'ARS', current_date + 2 from item_hierro$$, '23514');
select pg_temp.falla($$insert into public.gastos (presupuesto_item_id, descripcion, monto, moneda, tipo_cambio)
  select id, 'x', 10, 'ARS', 1200 from item_hierro$$, '23514');
select pg_temp.falla($$insert into public.gastos (presupuesto_item_id, descripcion, monto, moneda, tipo_cambio, tipo_cambio_origen)
  select id, 'x', 10, 'ARS', -1, 'manual' from item_hierro$$, '23514');
select pg_temp.falla($$insert into public.gastos (presupuesto_item_id, descripcion, monto, moneda)
  select id, repeat('x', 201), 10, 'ARS' from item_hierro$$, '23514');
select pg_temp.falla($$insert into public.presupuesto_items (obra_id, rubro_id, monto, moneda)
  select id, 1, -1, 'ARS' from public.obras limit 1$$, '23514');
select pg_temp.falla($$insert into public.presupuesto_items (obra_id, rubro_id, monto, moneda)
  select id, 999999, 10, 'ARS' from public.obras limit 1$$, '23503');
select pg_temp.ok(true, 'integridad: montos, descripción, moneda, fecha, cotización, rubro');

-- Gastos por ítem (#35, CA-34): sin ítem, ítem inexistente, de otra obra o borrado: no.
select pg_temp.falla($$insert into public.gastos (obra_id, rubro_id, descripcion, monto, moneda)
  select obra_id, rubro_id, 'x', 10, 'ARS' from item_hierro$$, '23503');
select pg_temp.falla($$insert into public.gastos (presupuesto_item_id, descripcion, monto, moneda)
  values (999999, 'x', 10, 'ARS')$$, '23503');
select pg_temp.falla($$insert into public.gastos (presupuesto_item_id, obra_id, descripcion, monto, moneda)
  select i.id, o.id, 'x', 10, 'ARS' from item_hierro i, public.obras o where o.nombre = 'Obra ajena'$$, '23514');
insert into public.presupuesto_items (obra_id, rubro_id, descripcion, monto, moneda, anulado)
  select o.id, 1, 'Ítem borrado', 0, 'ARS', true from public.obras o where o.nombre = 'Obra RLS';
select pg_temp.falla($$insert into public.gastos (presupuesto_item_id, descripcion, monto, moneda)
  select id, 'x', 10, 'ARS' from public.presupuesto_items where descripcion = 'Ítem borrado'$$, '23514');
select pg_temp.falla($$update public.gastos set rubro_id = rubro_id$$, '42501');
select pg_temp.ok(true, 'gastos por ítem: siempre con un ítem vigente de la misma obra');

-- #25 · Editar un gasto: se mueve solo a un ítem vigente de la misma obra.
insert into public.presupuesto_items (obra_id, rubro_id, descripcion, monto, moneda)
  select o.id, r.id, 'Ítem ajeno', 0, 'ARS' from public.obras o, public.rubros r
  where o.nombre = 'Obra ajena' and r.nombre = 'Pintura';
insert into public.presupuesto_items (obra_id, rubro_id, descripcion, monto, moneda)
  select o.id, r.id, 'Destino', 0, 'ARS' from public.obras o, public.rubros r
  where o.nombre = 'Obra RLS' and r.nombre = 'Revoques';
select pg_temp.falla($$update public.gastos set presupuesto_item_id =
  (select id from public.presupuesto_items where descripcion = 'Ítem ajeno')
  where descripcion = 'Hierro'$$, '23514');
select pg_temp.falla($$update public.gastos set presupuesto_item_id =
  (select id from public.presupuesto_items where descripcion = 'Ítem borrado')
  where descripcion = 'Hierro'$$, '23514');
update public.gastos set presupuesto_item_id =
  (select id from public.presupuesto_items where descripcion = 'Destino')
  where descripcion = 'Hierro';
select pg_temp.ok((select g.rubro_id = r.id and g.editado_por = '00000000-0000-0000-0000-00000000000a'
                          and g.editado_en is not null
                   from public.gastos g, public.rubros r
                   where g.descripcion = 'Hierro' and r.nombre = 'Revoques'),
                  'editar gasto: moverlo a otro ítem de la obra toma su rubro y queda registrado');
update public.gastos set presupuesto_item_id = (select id from item_hierro),
  fecha = fecha - 1, proveedor = 'Hierros Sur', monto = 350000, moneda = 'ARS'
  where descripcion = 'Hierro';
-- R7 en la base: no se mueve ni se carga un gasto en un ítem de rubro desactivado;
-- un gasto que ya estaba ahí se sigue editando sin moverlo.
insert into public.rubros (nombre, orden) values ('Rubro viejo', 900);
insert into public.presupuesto_items (obra_id, rubro_id, descripcion, monto, moneda)
  select o.id, r.id, 'En rubro viejo', 0, 'ARS' from public.obras o, public.rubros r
  where o.nombre = 'Obra RLS' and r.nombre = 'Rubro viejo';
insert into public.gastos (presupuesto_item_id, descripcion, monto, moneda)
  select id, 'Histórico', 5, 'ARS' from public.presupuesto_items where descripcion = 'En rubro viejo';
update public.rubros set activo = false where nombre = 'Rubro viejo';
select pg_temp.falla($$update public.gastos set presupuesto_item_id =
  (select id from public.presupuesto_items where descripcion = 'En rubro viejo')
  where descripcion = 'Hierro'$$, '23514');
select pg_temp.falla($$insert into public.gastos (presupuesto_item_id, descripcion, monto, moneda)
  select id, 'Nuevo', 5, 'ARS' from public.presupuesto_items where descripcion = 'En rubro viejo'$$,
  '23514');
update public.gastos set monto = 6, presupuesto_item_id = presupuesto_item_id
  where descripcion = 'Histórico';
select pg_temp.ok((select monto = 6 from public.gastos where descripcion = 'Histórico'),
                  'rubro desactivado: no recibe gastos nuevos ni movidos; los que ya tiene se editan');
select pg_temp.falla($$update public.gastos set creado_por = null$$, '42501');
select pg_temp.falla($$update public.gastos set editado_por = null$$, '42501');
select pg_temp.falla($$update public.gastos set created_at = now()$$, '42501');
select pg_temp.falla($$update public.gastos set fecha = current_date + 2 where descripcion = 'Hierro'$$, '23514');
select pg_temp.ok((select proveedor = 'Hierros Sur' and g.rubro_id = i.rubro_id
                   from public.gastos g join item_hierro i on i.id = g.presupuesto_item_id
                   where g.descripcion = 'Hierro'),
                  'editar gasto: fecha, proveedor, monto y moneda sí; obra, autor y registro no');

-- Monto 0 en ítems (D9) y un solo «Imprevistos» vigente por obra (R12).
insert into public.presupuesto_items (obra_id, rubro_id, descripcion, monto, moneda, es_imprevistos)
  select id, 1, 'Imprevistos', 0, 'ARS', true from public.obras where nombre = 'Obra RLS';
select pg_temp.falla($$insert into public.presupuesto_items (obra_id, rubro_id, monto, moneda, es_imprevistos)
  select id, 1, 0, 'ARS', true from public.obras where nombre = 'Obra RLS'$$, '23505');
update public.presupuesto_items set anulado = true
  where es_imprevistos and obra_id = (select id from public.obras where nombre = 'Obra RLS');
insert into public.presupuesto_items (obra_id, rubro_id, monto, moneda, es_imprevistos)
  select id, 1, 0, 'ARS', true from public.obras where nombre = 'Obra RLS';
select pg_temp.falla($$update public.presupuesto_items set es_imprevistos = false$$, '42501');
select pg_temp.ok(true, 'ítems: monto 0 permitido; un «Imprevistos» vigente por obra; se puede volver a crear');

-- #53: la base no acepta caracteres invisibles, de control ni marcadores, aunque
-- se saltee la app; los textos normales (tildes, ñ, n.º, m², emojis) sí.
select pg_temp.falla($$insert into public.bitacora (obra_id, nota)
  select id, E'Llegó\u200B el hierro' from public.obras where nombre = 'Obra RLS'$$, '23514');
select pg_temp.falla($$insert into public.bitacora (obra_id, nota)
  select id, 'Nota [[DATOS]] falsa' from public.obras where nombre = 'Obra RLS'$$, '23514');
select pg_temp.falla($$update public.obras set cliente = E'Pérez\u202E' where nombre = 'Obra RLS'$$, '23514');
select pg_temp.falla($$insert into public.rubros (nombre) values (E'Pileta\x07')$$, '23514');
select pg_temp.falla($$insert into public.rubros (nombre) values (E'Pileta\u0085')$$, '23514');
select pg_temp.falla($$insert into public.rubros (nombre) values (E'Pile\tta')$$, '23514');
select pg_temp.falla($$insert into public.rubros (nombre) values (E'Pileta\u061C')$$, '23514');
select pg_temp.falla($$insert into public.rubros (nombre) values (E'Pileta\u2028')$$, '23514');
select pg_temp.falla($$insert into public.rubros (nombre) values (E'Pileta\U000E0041')$$, '23514');
insert into public.bitacora (obra_id, nota)
  select id, E'Llegó el hierro: 12 m² y caño n.º 3 — «ñandú» 👍\nSegunda línea' from public.obras
   where nombre = 'Obra RLS';
select pg_temp.ok((select count(*) = 1 from public.bitacora where nota like 'Llegó el hierro: 12 m²%'),
                  'texto limpio #53: invisibles y marcadores rechazados en la base; texto normal intacto');

-- Rubros: alta preparada, nombres únicos sin importar mayúsculas ni espacios.
insert into public.rubros (nombre, orden) values ('Piscina', 500);
select pg_temp.falla($$insert into public.rubros (nombre) values ('  piscina ')$$, '23505');
select pg_temp.falla($$insert into public.rubros (nombre) values ('ESTRUCTURA')$$, '23505');
select pg_temp.falla($$insert into public.rubros (nombre) values ('x')$$, '23514');
select pg_temp.falla($$insert into public.rubros (nombre) values ('Mamposteria')$$, '23505');
select pg_temp.falla($$insert into public.rubros (nombre) values ('MAMPOSTERÍA')$$, '23505');
select pg_temp.falla($$insert into public.rubros (nombre) values ('Steel   Frame')$$, '23505');
select pg_temp.falla($$insert into public.rubros (nombre) values ('instalacion  ELECTRICA')$$, '23505');
update public.rubros set activo = false where nombre = 'Piscina';
select pg_temp.ok(true, 'rubros: alta, duplicados (mayúsculas, tildes, espacios) rechazados, desactivar');

-- #49 · Rubros: se ordenan y se reactivan; el nombre no se edita; «Otros» no se desactiva.
update public.rubros set orden = 501, activo = true where nombre = 'Piscina';
select pg_temp.falla($$update public.rubros set nombre = 'Pileta' where nombre = 'Piscina'$$, '42501');
select pg_temp.falla($$update public.rubros set creado_por = null$$, '42501');
select pg_temp.falla($$update public.rubros set activo = false where nombre = 'Otros'$$, '23514');
select pg_temp.ok((select orden = 501 and activo from public.rubros where nombre = 'Piscina')
                  and (select activo from public.rubros where nombre = 'Otros'),
                  'rubros: orden y activo sí; nombre y autor no; «Otros» siempre activo');

-- #49 · Detalle de la obra: se editan los datos del alta; autor, fecha e id no.
update public.obras set nombre = 'Obra RLS editada', cliente = 'Pérez', direccion = 'Calle 1',
  municipio = 'Quilmes', tipo = 'Reforma', estado = 'En curso', avance = 10, responsable = 'Caro',
  fecha_inicio = current_date, fecha_fin_estimada = current_date + 30, presupuesto = 1000,
  moneda = 'USD'
  where nombre = 'Obra RLS';
update public.obras set nombre = 'Obra RLS' where nombre = 'Obra RLS editada';
select pg_temp.falla($$update public.obras set creado_por = null where nombre = 'Obra RLS'$$, '42501');
select pg_temp.falla($$update public.obras set created_at = now() where nombre = 'Obra RLS'$$, '42501');
select pg_temp.falla($$update public.obras set nombre = '   ' where nombre = 'Obra RLS'$$, '23514');
select pg_temp.falla($$update public.obras set presupuesto = -1 where nombre = 'Obra RLS'$$, '23514');
select pg_temp.ok((select municipio = 'Quilmes' and moneda = 'USD' and presupuesto = 1000
                          and creado_por = '00000000-0000-0000-0000-00000000000a'
                   from public.obras where nombre = 'Obra RLS'),
                  'obras: todos los datos del alta se editan; autor y fecha de creación no; nombre no vacío');

-- #37 · Proveedores: lista compartida, nombre único, datos validados, sin DELETE.
insert into public.proveedores (nombre, telefono, email, web, cuit, rubro_ids)
  select 'Hierros RLS', '221 555-1234', 'ventas@hierros.test', 'https://hierros.test', '30-71234567-1',
         array[(select id from public.rubros where nombre = 'Estructura')];
select pg_temp.ok((select creado_por from public.proveedores where nombre = 'Hierros RLS')
                  = '00000000-0000-0000-0000-00000000000a', 'proveedor firmado por su autor');
select pg_temp.falla($$insert into public.proveedores (nombre) values ('  HIERROS   rls ')$$, '23505');
select pg_temp.falla($$insert into public.proveedores (nombre) values ('x')$$, '23514');
select pg_temp.falla($$insert into public.proveedores (nombre, email) values ('Mail malo', 'no-es-mail')$$, '23514');
select pg_temp.falla($$insert into public.proveedores (nombre, email)
  values ('Mail con bcc', 'x@example.com?bcc=atacante%40evil.test')$$, '23514');
select pg_temp.falla($$insert into public.proveedores (nombre, web) values ('Web mala', 'http://x.test')$$, '23514');
select pg_temp.falla($$insert into public.proveedores (nombre, web) values ('Web js', 'javascript:alert(1)')$$, '23514');
select pg_temp.falla($$insert into public.proveedores (nombre, cuit) values ('Cuit malo', '123')$$, '23514');
select pg_temp.falla($$insert into public.proveedores (nombre, telefono) values ('Tel malo', 'llamame')$$, '23514');
select pg_temp.falla($$insert into public.proveedores (nombre, telefono) values ('Tel sin dígitos', '++++++')$$, '23514');
select pg_temp.falla($$insert into public.proveedores (nombre, telefono) values ('Tel corto', '(221) 55')$$, '23514');
select pg_temp.falla($$insert into public.proveedores (nombre, rubro_ids) values ('Rubro malo', '{999999}')$$, '23503');
select pg_temp.falla($$update public.proveedores set creado_por = null where nombre = 'Hierros RLS'$$, '42501');
insert into public.proveedores (nombre, creado_por, created_at)
  values ('Firmado por otro', '00000000-0000-0000-0000-00000000000b', '2001-01-01');
select pg_temp.ok((select creado_por = '00000000-0000-0000-0000-00000000000a'
                          and created_at > now() - interval '1 hour'
                     from public.proveedores where nombre = 'Firmado por otro'),
                  'proveedores: la base pone el autor (el login) y la fecha de creación');
select pg_temp.falla($$update public.proveedores set created_at = now() where nombre = 'Hierros RLS'$$, '42501');
delete from public.proveedores where nombre = 'Hierros RLS';
select pg_temp.ok((select count(*) from public.proveedores where nombre = 'Hierros RLS') = 1,
                  'proveedores: nombre único y datos validados en la base; sin DELETE; autor fijo');

-- Calificaciones: una por socio; cada uno escribe solo la suya.
insert into public.proveedor_calificaciones (proveedor_id, estrellas, comentario, autor)
  select id, 4, 'Cumple', 'b@atrium.test' from public.proveedores where nombre = 'Hierros RLS';
select pg_temp.falla($$update public.proveedor_calificaciones set autor = 'b@atrium.test'$$, '42501');
select pg_temp.falla($$insert into public.proveedor_calificaciones (proveedor_id, estrellas)
  select id, 5 from public.proveedores where nombre = 'Hierros RLS'$$, '23505');
select pg_temp.falla($$insert into public.proveedor_calificaciones (proveedor_id, estrellas, creado_por)
  select id, 5, '00000000-0000-0000-0000-00000000000b' from public.proveedores where nombre = 'Hierros RLS'$$,
  '42501');
select pg_temp.falla($$update public.proveedor_calificaciones set estrellas = 6$$, '23514');
select pg_temp.falla($$update public.proveedor_calificaciones set creado_por = null$$, '42501');
update public.proveedor_calificaciones set estrellas = 5;
select pg_temp.falla($$update public.proveedor_calificaciones set created_at = '2001-01-01'$$, '42501');
select pg_temp.ok((select estrellas = 5 and editado_en is not null and autor = 'a@atrium.test'
                     from public.proveedor_calificaciones),
                  'calificaciones: 1 a 5, una por socio, firmadas con el mail del login (no el que se mande); queda la fecha de edición');

-- El gasto elige un proveedor vigente; uno eliminado (archivado) no se elige,
-- pero los gastos que ya lo tenían lo conservan y se siguen editando.
insert into public.gastos (presupuesto_item_id, descripcion, monto, moneda, proveedor_id)
  select (select id from item_hierro), 'Con proveedor', 10, 'ARS', id
  from public.proveedores where nombre = 'Hierros RLS';
update public.proveedores set archivado = true where nombre = 'Hierros RLS';
select pg_temp.falla($$insert into public.gastos (presupuesto_item_id, descripcion, monto, moneda, proveedor_id)
  select (select id from item_hierro), 'Otro', 10, 'ARS', id
  from public.proveedores where nombre = 'Hierros RLS'$$, '23514');
update public.gastos set monto = 11 where descripcion = 'Con proveedor';
select pg_temp.falla($$insert into public.proveedor_calificaciones (proveedor_id, estrellas)
  select id, 3 from public.proveedores where nombre = 'Hierros RLS'$$, '23514');
update public.proveedor_calificaciones set comentario = 'Sigue cumpliendo';
update public.proveedores set archivado = false where nombre = 'Hierros RLS';
insert into public.gastos (presupuesto_item_id, descripcion, monto, moneda)
  select id, 'Sin proveedor todavía', 10, 'ARS' from item_hierro;
update public.gastos set proveedor_id = (select id from public.proveedores where nombre = 'Hierros RLS')
  where descripcion = 'Sin proveedor todavía';
select pg_temp.ok((select editado_en is not null and editado_por = '00000000-0000-0000-0000-00000000000a'
                     from public.gastos where descripcion = 'Sin proveedor todavía'),
                  'gastos: cambiar el proveedor queda registrado como edición');
update public.gastos set anulado = true where descripcion in ('Con proveedor', 'Sin proveedor todavía');
select pg_temp.falla($$update public.gastos set proveedor_id = null where descripcion = 'Con proveedor'$$, '23514');
select pg_temp.ok(true, 'proveedor eliminado: no se elige en gastos ni recibe calificaciones nuevas; lo ya cargado se edita');

-- Editar ítems (F-03 R9): solo rubro, descripción, monto, moneda y cotización.
-- Si cambia el rubro, los gastos del ítem lo siguen (CA-35).
update public.presupuesto_items set monto = 1500, moneda = 'USD',
  rubro_id = (select id from public.rubros where nombre = 'Fundaciones'),
  tipo_cambio = 1180, tipo_cambio_origen = 'manual'
  where id = (select id from item_hierro);
select pg_temp.ok((select g.rubro_id = r.id from public.gastos g, public.rubros r
                   where g.descripcion = 'Hierro' and r.nombre = 'Fundaciones'),
                  'cambiar el rubro del ítem mueve sus gastos a ese rubro');
select pg_temp.falla($$update public.presupuesto_items set obra_id = obra_id$$, '42501');
select pg_temp.falla($$update public.presupuesto_items set fecha = fecha - 1$$, '42501');
select pg_temp.falla($$update public.presupuesto_items set creado_por = null$$, '42501');
select pg_temp.falla($$update public.presupuesto_items set id = id$$, '428C9');  -- identity: nunca se escribe
select pg_temp.falla($$update public.gastos set obra_id = obra_id$$, '42501');
select pg_temp.ok((select monto = 1500 and moneda = 'USD' from item_hierro),
                  'editar ítems: campos permitidos sí; obra, fecha, autor e id no; gasto sin cambiar de obra');

-- Corregir cotización y anular (update permitido); borrar, nunca.
update public.gastos set tipo_cambio = 1180, tipo_cambio_origen = 'manual' where descripcion = 'Hierro';
delete from public.gastos;
delete from public.presupuesto_items;
delete from public.rubros;
select pg_temp.ok((select count(*) from public.gastos where descripcion = 'Hierro') = 1
                  and (select count(*) from public.presupuesto_items i join public.obras o on o.id = i.obra_id
                       where o.nombre = 'Obra RLS') = 6
                  and (select count(*) from public.rubros where nombre not like 'Acme%' and nombre not like 'Sin nombre%') = 20,
                  'sin DELETE: gastos, presupuesto y rubros no se borran');

-- Borrar (anular) un ítem anula también sus gastos (R12b).
update public.presupuesto_items set anulado = true where id = (select id from item_hierro);
select pg_temp.ok((select anulado from public.gastos where descripcion = 'Hierro'),
                  'borrar un ítem anula sus gastos, que siguen en la base');
select pg_temp.falla($$update public.gastos set anulado = false where descripcion = 'Hierro'$$, '23514');
select pg_temp.falla($$update public.gastos set descripcion = 'otra' where descripcion = 'Hierro'$$, '23514');
select pg_temp.falla($$update public.presupuesto_items set anulado = false
  where id = (select id from item_hierro)$$, '23514');
select pg_temp.ok((select anulado from public.gastos where descripcion = 'Hierro'),
                  'anular es definitivo: ni el gasto ni su ítem borrado se reactivan');

-- ----- usuario B: comparte todo con el equipo (D6) -----
reset role;
select pg_temp.como('authenticated', '00000000-0000-0000-0000-00000000000b');
select pg_temp.ok((select count(*) from public.gastos where descripcion = 'Hierro') = 1
                  and (select count(*) from public.presupuesto_items) >= 4,
                  'equipo: B ve gastos y presupuesto de A');
update public.proveedor_calificaciones set estrellas = 1;
select pg_temp.ok((select count(*) from public.proveedores where nombre = 'Hierros RLS') = 1
                  and (select estrellas from public.proveedor_calificaciones
                        where creado_por = '00000000-0000-0000-0000-00000000000a') = 5,
                  'equipo: B ve los proveedores y calificaciones de A, pero no cambia la calificación de A');

-- ----- anónimo (F-03-CA-13) -----
reset role;
select pg_temp.como('anon', null);
select pg_temp.ok((select count(*) from public.rubros) = 0
                  and (select count(*) from public.gastos) = 0
                  and (select count(*) from public.presupuesto_items) = 0,
                  'anon: no ve rubros, gastos ni presupuesto');
select pg_temp.falla($$insert into public.rubros (nombre) values ('Intruso')$$, '42501');
select pg_temp.falla($$insert into public.gastos (presupuesto_item_id, descripcion, monto, moneda)
  values (1, 'x', 10, 'ARS')$$, '42501');
select pg_temp.falla($$insert into public.presupuesto_items (obra_id, rubro_id, monto, moneda)
  values (1, 1, 10, 'ARS')$$, '42501');
select pg_temp.falla($$update public.gastos set monto = 1$$, '42501');
select pg_temp.falla($$update public.obras set nombre = 'x'$$, '42501');
select pg_temp.ok((select count(*) from public.proveedores) = 0
                  and (select count(*) from public.proveedor_calificaciones) = 0,
                  'anon: no ve proveedores ni calificaciones');
select pg_temp.falla($$insert into public.proveedores (nombre) values ('Intruso')$$, '42501');
select pg_temp.falla($$insert into public.proveedor_calificaciones (proveedor_id, estrellas) values (1, 5)$$, '42501');
select pg_temp.falla($$update public.proveedores set nombre = 'x'$$, '42501');
select pg_temp.falla($$update public.rubros set orden = 1$$, '42501');
reset role;
select pg_temp.ok((select monto from public.gastos where descripcion = 'Hierro') = 350000,
                  'anon: no puede crear ni editar');
