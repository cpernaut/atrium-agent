#!/usr/bin/env bash
# Two connections at once (revisión PR #38): a gasto being inserted and its item
# being edited or deleted must never leave the gasto with an old rubro or alive
# under a deleted item. Usage: tests/sql/test_concurrencia.sh <database>
set -euo pipefail
DB="$1"
q() { psql -X -q -At -v ON_ERROR_STOP=1 -d "$DB" "$@"; }
falla() { echo "FALLÓ: $1"; exit 1; }

nuevo_item() {
  q -c "insert into public.presupuesto_items (obra_id, rubro_id, descripcion, monto, moneda)
        select o.id, r.id, '$1', 0, 'ARS' from public.obras o, public.rubros r
        where r.nombre = 'Pintura' order by o.id limit 1 returning id" | head -1
}
gasto_sql() {
  echo "insert into public.gastos (presupuesto_item_id, descripcion, monto, moneda)
        values ($1, '$2', 10, 'ARS');"
}

# 1) El gasto se inserta primero (transacción abierta): cambiar el rubro del ítem
#    espera a que termine, y después el gasto sigue al ítem.
ITEM=$(nuevo_item "Concurrencia rubro")
q -c "begin; $(gasto_sql "$ITEM" 'conc-1') select pg_sleep(2); commit;" >/dev/null &
sleep 0.7
if q -c "set lock_timeout = '300ms';
         update public.presupuesto_items set rubro_id = (select id from public.rubros where nombre = 'Revoques')
         where id = $ITEM" >/dev/null 2>&1; then
  falla "el ítem se editó mientras se insertaba un gasto (no hay bloqueo)"
fi
wait
q -c "update public.presupuesto_items set rubro_id = (select id from public.rubros where nombre = 'Revoques')
      where id = $ITEM" >/dev/null
[ "$(q -c "select r.nombre from public.gastos g join public.rubros r on r.id = g.rubro_id
          where g.descripcion = 'conc-1'")" = "Revoques" ] || falla "el gasto quedó con el rubro viejo"
echo "OK  concurrencia: el ítem espera al gasto que se inserta y después le pasa el rubro"

# 2) El ítem se está cambiando de rubro (sin confirmar): el gasto espera y toma
#    el rubro nuevo.
ITEM=$(nuevo_item "Concurrencia rubro 2")
q -c "begin; update public.presupuesto_items set rubro_id = (select id from public.rubros where nombre = 'Revoques')
      where id = $ITEM; select pg_sleep(2); commit;" >/dev/null &
sleep 0.7
q -c "$(gasto_sql "$ITEM" 'conc-2')" >/dev/null
wait
[ "$(q -c "select r.nombre from public.gastos g join public.rubros r on r.id = g.rubro_id
          where g.descripcion = 'conc-2'")" = "Revoques" ] || falla "el gasto tomó el rubro viejo del ítem"
echo "OK  concurrencia: un gasto cargado mientras cambia el rubro toma el rubro nuevo"

# 3) El ítem se está borrando (sin confirmar): el gasto espera y se rechaza.
ITEM=$(nuevo_item "Concurrencia borrado")
q -c "begin; update public.presupuesto_items set anulado = true where id = $ITEM;
      select pg_sleep(2); commit;" >/dev/null &
sleep 0.7
if q -c "$(gasto_sql "$ITEM" 'conc-3')" >/dev/null 2>&1; then
  falla "se creó un gasto vigente bajo un ítem que se estaba borrando"
fi
wait
[ "$(q -c "select count(*) from public.gastos where descripcion = 'conc-3'")" = "0" ] || falla "quedó el gasto"
echo "OK  concurrencia: un gasto cargado mientras se borra su ítem se rechaza"
