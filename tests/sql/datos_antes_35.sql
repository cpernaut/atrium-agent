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
               ('Pintura', 'Gasto previo de una letra', false, 'Y'),
               ('Pintura', E'Gasto previo con invisibles\u200B y [[marcas]]', false, null),
               ('Pintura', 'Gasto de Pinturas Z', false, 'Pinturas Z'),
               ('Pintura', 'Gasto de Pinturas Z con invisible', false, E'Pinturas\u200B Z'))
         as x(rubro, descripcion, anulado, proveedor)
 where o.nombre = 'Obra previa' and r.nombre = x.rubro;
-- #53: rubros que solo difieren por un invisible o un control C1.
insert into public.rubros (nombre) values ('Acme'), (E'Acme\u200B'), (E'Ac\u0085me'),
    ('Acme (2)'), (E'\u200B\u200B\u200B'), (E'\u200B\u200C');
-- #53: una obra cuyo nombre son solo invisibles, y un gasto igual.
insert into public.obras (nombre, cliente) values (E'\u200B\u2060', E'\t\u061C');
insert into public.gastos (obra_id, rubro_id, descripcion, monto, moneda)
select o.id, r.id, E'\u200B', 5, 'USD' from public.obras o, public.rubros r
 where o.nombre = 'Obra previa' and r.nombre = 'Pintura';
