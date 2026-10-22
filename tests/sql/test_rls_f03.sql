-- Security and integrity checks for F-03 on a real Postgres.
-- Every check raises on failure; run with ON_ERROR_STOP.
\set ON_ERROR_STOP 1

create function pg_temp.como(rol text, uid text) returns void language plpgsql as $$
begin
  perform set_config('request.jwt.claims',
    case when uid is null then '{"role":"anon"}'
         else json_build_object('sub', uid, 'role', rol)::text end, false);
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
select pg_temp.ok((select count(*) from public.rubros) = 18, 'precarga: 18 rubros');
select pg_temp.ok(exists(select 1 from public.rubros where nombre = 'Steel frame' and orden = 50),
                  'precarga: Steel frame');

-- ----- usuario A logueado -----
select pg_temp.como('authenticated', '00000000-0000-0000-0000-00000000000a');
insert into public.obras (nombre) values ('Obra RLS');
select pg_temp.ok((select creado_por from public.obras where nombre = 'Obra RLS')
                  = '00000000-0000-0000-0000-00000000000a', 'obra firmada por su autor');

insert into public.presupuesto_items (obra_id, rubro_id, monto, moneda, tipo_cambio, tipo_cambio_origen)
  select o.id, r.id, 1000, 'ARS', 1200, 'auto' from public.obras o, public.rubros r
  where o.nombre = 'Obra RLS' and r.nombre = 'Estructura';
insert into public.gastos (obra_id, rubro_id, descripcion, monto, moneda)
  select o.id, r.id, 'Hierro', 350000, 'ARS' from public.obras o, public.rubros r
  where o.nombre = 'Obra RLS' and r.nombre = 'Estructura';
select pg_temp.ok((select fecha = current_date and not anulado and tipo_cambio is null
                   from public.gastos where descripcion = 'Hierro'),
                  'gasto: defaults (fecha hoy, no anulado, sin cotización)');

-- Integridad (F-03-CA-10): la base rechaza datos inválidos aunque se saltee la app.
select pg_temp.falla($$insert into public.gastos (obra_id, rubro_id, descripcion, monto, moneda)
  select id, 1, 'x', 0, 'ARS' from public.obras limit 1$$, '23514');
select pg_temp.falla($$insert into public.gastos (obra_id, rubro_id, descripcion, monto, moneda)
  select id, 1, 'x', -5, 'ARS' from public.obras limit 1$$, '23514');
select pg_temp.falla($$insert into public.gastos (obra_id, rubro_id, descripcion, monto, moneda)
  select id, 1, '   ', 10, 'ARS' from public.obras limit 1$$, '23514');
select pg_temp.falla($$insert into public.gastos (obra_id, rubro_id, descripcion, monto, moneda)
  select id, 1, null, 10, 'ARS' from public.obras limit 1$$, '23502');
select pg_temp.falla($$insert into public.gastos (obra_id, rubro_id, descripcion, monto, moneda)
  select id, 1, 'x', 10, 'EUR' from public.obras limit 1$$, '23514');
select pg_temp.falla($$insert into public.gastos (obra_id, rubro_id, descripcion, monto, moneda, fecha)
  select id, 1, 'x', 10, 'ARS', current_date + 2 from public.obras limit 1$$, '23514');
select pg_temp.falla($$insert into public.gastos (obra_id, rubro_id, descripcion, monto, moneda, tipo_cambio)
  select id, 1, 'x', 10, 'ARS', 1200 from public.obras limit 1$$, '23514');
select pg_temp.falla($$insert into public.gastos (obra_id, rubro_id, descripcion, monto, moneda, tipo_cambio, tipo_cambio_origen)
  select id, 1, 'x', 10, 'ARS', -1, 'manual' from public.obras limit 1$$, '23514');
select pg_temp.falla($$insert into public.gastos (obra_id, rubro_id, descripcion, monto, moneda)
  select id, 999999, 'x', 10, 'ARS' from public.obras limit 1$$, '23503');
select pg_temp.falla($$insert into public.gastos (obra_id, rubro_id, descripcion, monto, moneda)
  select id, 1, repeat('x', 201), 10, 'ARS' from public.obras limit 1$$, '23514');
select pg_temp.falla($$insert into public.presupuesto_items (obra_id, rubro_id, monto, moneda)
  select id, 1, 0, 'ARS' from public.obras limit 1$$, '23514');
select pg_temp.ok(true, 'integridad: montos, descripción, moneda, fecha, cotización, rubro');

-- Rubros: alta preparada, nombres únicos sin importar mayúsculas ni espacios.
insert into public.rubros (nombre, orden) values ('Piscina', 500);
select pg_temp.falla($$insert into public.rubros (nombre) values ('  piscina ')$$, '23505');
select pg_temp.falla($$insert into public.rubros (nombre) values ('ESTRUCTURA')$$, '23505');
select pg_temp.falla($$insert into public.rubros (nombre) values ('x')$$, '23514');
update public.rubros set activo = false where nombre = 'Piscina';
select pg_temp.ok(true, 'rubros: alta, duplicados rechazados, desactivar');

-- Anular y corregir cotización (update permitido); borrar, nunca.
update public.gastos set anulado = true where descripcion = 'Hierro';
update public.gastos set tipo_cambio = 1180, tipo_cambio_origen = 'manual' where descripcion = 'Hierro';
delete from public.gastos;
delete from public.presupuesto_items;
delete from public.rubros;
select pg_temp.ok((select count(*) from public.gastos) = 1
                  and (select count(*) from public.presupuesto_items) = 1
                  and (select count(*) from public.rubros) = 19,
                  'sin DELETE: gastos, presupuesto y rubros no se borran');

-- ----- usuario B: comparte todo con el equipo (D6) -----
reset role;
select pg_temp.como('authenticated', '00000000-0000-0000-0000-00000000000b');
select pg_temp.ok((select count(*) from public.gastos) = 1
                  and (select count(*) from public.presupuesto_items) = 1,
                  'equipo: B ve gastos y presupuesto de A');

-- ----- anónimo (F-03-CA-13) -----
reset role;
select pg_temp.como('anon', null);
select pg_temp.ok((select count(*) from public.rubros) = 0
                  and (select count(*) from public.gastos) = 0
                  and (select count(*) from public.presupuesto_items) = 0,
                  'anon: no ve rubros, gastos ni presupuesto');
select pg_temp.falla($$insert into public.rubros (nombre) values ('Intruso')$$, '42501');
select pg_temp.falla($$insert into public.gastos (obra_id, rubro_id, descripcion, monto, moneda)
  values (1, 1, 'x', 10, 'ARS')$$, '42501');
update public.gastos set monto = 1;
reset role;
select pg_temp.ok((select monto from public.gastos) = 350000, 'anon: no puede crear ni editar');
