#!/usr/bin/env bash
# Run supabase_schema.sql on a fresh local Postgres database (twice, to prove it
# is idempotent) and then the security checks. Usage:
#   PGHOST=/path/to/socket PGPORT=5432 PGUSER=postgres tests/sql/run.sh
set -euo pipefail
cd "$(dirname "$0")/../.."
DB="atrium_schema_test"
PSQL=(psql -X -q -v ON_ERROR_STOP=1)
# Every line «OK …» or «FALLÓ …» also goes to the run's Summary page in GitHub.
SALIDA=$(mktemp)
resumen() {
  [ -n "${GITHUB_STEP_SUMMARY:-}" ] || return 0
  {
    echo "## Esquema y seguridad en Postgres"
    echo
    if grep -q "FALL\|ERROR" "$SALIDA" || [ "$1" != 0 ]; then
      echo "**❌ Falló un chequeo**"
    else
      echo "**✅ Todos los chequeos pasaron** · $(grep -c '^OK' "$SALIDA") chequeos"
    fi
    echo
    echo "| | Qué se verifica |"
    echo "|---|---|"
    sed -n 's/^OK  */| ✅ | /p; s/^FALLÓ: */| ❌ | /p; s/^.*ERROR: */| ❌ | /p' "$SALIDA" \
      | sed 's/$/ |/'
    if [ "$1" != 0 ] && ! grep -q "FALL\|ERROR" "$SALIDA"; then
      echo "| ❌ | El script se cortó con código $1: ver el log del paso |"
    fi
  } >> "$GITHUB_STEP_SUMMARY"
}

principal() {
"${PSQL[@]}" -d postgres -c "drop database if exists $DB" -c "create database $DB encoding 'UTF8' lc_collate 'C.UTF-8' lc_ctype 'C.UTF-8' template template0" >/dev/null 2>&1
"${PSQL[@]}" -d "$DB" -f tests/sql/supabase_stub.sql >/dev/null
# Base como estaba antes de #35, con datos: obras, un ítem y gastos sin ítem.
"${PSQL[@]}" -d "$DB" -f tests/sql/esquema_antes_35.sql 2>/dev/null
"${PSQL[@]}" -d "$DB" -f tests/sql/datos_antes_35.sql >/dev/null
# Actualización: el esquema nuevo migra esos datos (y se puede correr varias veces).
"${PSQL[@]}" -d "$DB" -f supabase_schema.sql 2>/dev/null
"${PSQL[@]}" -d "$DB" -f supabase_schema.sql 2>/dev/null
echo "OK  actualización desde el esquema anterior a #35, con datos, dos veces sin errores"
# #37: renombrar un proveedor migrado y volver a correr el esquema no recrea el nombre viejo.
"${PSQL[@]}" -d "$DB" -c "update public.proveedores set nombre = 'Hierros del Sur' where nombre = 'Hierros Sur'" >/dev/null
"${PSQL[@]}" -d "$DB" -f supabase_schema.sql 2>/dev/null
# Instalación desde cero (proyecto nuevo), también dos veces.
"${PSQL[@]}" -d postgres -c "drop database if exists ${DB}_nuevo" -c "create database ${DB}_nuevo encoding 'UTF8' lc_collate 'C.UTF-8' lc_ctype 'C.UTF-8' template template0" >/dev/null 2>&1
"${PSQL[@]}" -d "${DB}_nuevo" -f tests/sql/supabase_stub.sql >/dev/null
"${PSQL[@]}" -d "${DB}_nuevo" -f supabase_schema.sql 2>/dev/null
"${PSQL[@]}" -d "${DB}_nuevo" -f supabase_schema.sql 2>/dev/null
"${PSQL[@]}" -d postgres -c "drop database ${DB}_nuevo" >/dev/null
echo "OK  instalación desde cero, dos veces sin errores"
"${PSQL[@]}" -d "$DB" -At -f tests/sql/test_rls_f03.sql 2>&1 | grep -E "OK|FALL|ERROR" | sed 's/^.*NOTICE:  //'
tests/sql/test_concurrencia.sh "$DB"
"${PSQL[@]}" -d postgres -c "drop database $DB" >/dev/null
}

set +e
( set -e; principal ) 2>&1 | tee "$SALIDA"
ESTADO=${PIPESTATUS[0]}
resumen "$ESTADO"
rm -f "$SALIDA"
exit "$ESTADO"
