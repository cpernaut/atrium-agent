#!/usr/bin/env bash
# Run supabase_schema.sql on a fresh local Postgres database (twice, to prove it
# is idempotent) and then the security checks. Usage:
#   PGHOST=/path/to/socket PGPORT=5432 PGUSER=postgres tests/sql/run.sh
set -euo pipefail
cd "$(dirname "$0")/../.."
DB="atrium_schema_test"
PSQL=(psql -X -q -v ON_ERROR_STOP=1)
"${PSQL[@]}" -d postgres -c "drop database if exists $DB" -c "create database $DB encoding 'UTF8' lc_collate 'C.UTF-8' lc_ctype 'C.UTF-8' template template0" >/dev/null 2>&1
"${PSQL[@]}" -d "$DB" -f tests/sql/supabase_stub.sql >/dev/null
# Base como estaba antes de #35, con datos: obras, un ítem y gastos sin ítem.
"${PSQL[@]}" -d "$DB" -f tests/sql/esquema_antes_35.sql 2>/dev/null
"${PSQL[@]}" -d "$DB" -f tests/sql/datos_antes_35.sql >/dev/null
# Actualización: el esquema nuevo migra esos datos (y se puede correr varias veces).
"${PSQL[@]}" -d "$DB" -f supabase_schema.sql 2>/dev/null
"${PSQL[@]}" -d "$DB" -f supabase_schema.sql 2>/dev/null
echo "OK  actualización desde el esquema anterior a #35, con datos, dos veces sin errores"
# Instalación desde cero (proyecto nuevo), también dos veces.
"${PSQL[@]}" -d postgres -c "drop database if exists ${DB}_nuevo" -c "create database ${DB}_nuevo encoding 'UTF8' lc_collate 'C.UTF-8' lc_ctype 'C.UTF-8' template template0" >/dev/null 2>&1
"${PSQL[@]}" -d "${DB}_nuevo" -f tests/sql/supabase_stub.sql >/dev/null
"${PSQL[@]}" -d "${DB}_nuevo" -f supabase_schema.sql 2>/dev/null
"${PSQL[@]}" -d "${DB}_nuevo" -f supabase_schema.sql 2>/dev/null
"${PSQL[@]}" -d postgres -c "drop database ${DB}_nuevo" >/dev/null
echo "OK  instalación desde cero, dos veces sin errores"
"${PSQL[@]}" -d "$DB" -At -f tests/sql/test_rls_f03.sql 2>&1 | grep -E "OK|FALL|ERROR" | sed 's/^NOTICE:  //'
tests/sql/test_concurrencia.sh "$DB"
"${PSQL[@]}" -d postgres -c "drop database $DB" >/dev/null
