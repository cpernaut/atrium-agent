-- Datos con el esquema anterior a #35 (gastos sin ítem), para probar la migración.
\set ON_ERROR_STOP 1
insert into public.obras (nombre, presupuesto, moneda) values
    ('Obra previa', 50000, 'USD'),
    ('Obra previa sin presupuesto', null, 'ARS');
insert into public.presupuesto_items (obra_id, rubro_id, descripcion, monto, moneda)
select o.id, r.id, 'Hierro previo', 100, 'USD'
  from public.obras o, public.rubros r
 where o.nombre = 'Obra previa' and r.nombre = 'Estructura';
-- Proveedor escrito a mano (antes de #37): dos formas del mismo nombre y otro.
insert into public.gastos (obra_id, rubro_id, descripcion, monto, moneda, anulado, proveedor)
select o.id, r.id, x.descripcion, 10, 'USD', x.anulado, x.proveedor
  from public.obras o, public.rubros r,
       (values ('Estructura', 'Gasto previo con ítem', false, 'Hierros Sur'),
               ('Pintura', 'Gasto previo sin ítem', false, '  hierros   SUR '),
               ('Pintura', 'Gasto previo anulado', true, 'Pinturería X'),
               ('Pintura', 'Gasto previo de una letra', false, 'Y'))
         as x(rubro, descripcion, anulado, proveedor)
 where o.nombre = 'Obra previa' and r.nombre = x.rubro;
