-- Datos con el esquema anterior a #35 (gastos sin ítem), para probar la migración.
\set ON_ERROR_STOP 1
insert into public.obras (nombre, presupuesto, moneda) values
    ('Obra previa', 50000, 'USD'),
    ('Obra previa sin presupuesto', null, 'ARS');
insert into public.presupuesto_items (obra_id, rubro_id, descripcion, monto, moneda)
select o.id, r.id, 'Hierro previo', 100, 'USD'
  from public.obras o, public.rubros r
 where o.nombre = 'Obra previa' and r.nombre = 'Estructura';
insert into public.gastos (obra_id, rubro_id, descripcion, monto, moneda, anulado)
select o.id, r.id, x.descripcion, 10, 'USD', x.anulado
  from public.obras o, public.rubros r,
       (values ('Estructura', 'Gasto previo con ítem', false),
               ('Pintura', 'Gasto previo sin ítem', false),
               ('Pintura', 'Gasto previo anulado', true)) as x(rubro, descripcion, anulado)
 where o.nombre = 'Obra previa' and r.nombre = x.rubro;
