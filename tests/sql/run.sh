#!/usr/bin/env bash
# Run supabase_schema.sql on a fresh local Postgres database (twice, to prove it
# is idempotent) and then the security checks. Usage:
#   PGHOST=/path/to/socket PGPORT=5432 PGUSER=postgres tests/sql/run.sh
set -euo pipefail
cd "$(dirname "$0")/../.."
DB="atrium_schema_test"
PSQL=(psql -X -q -v ON_ERROR_STOP=1)
"${PSQL[@]}" -d postgres -c "drop database if exists $DB" -c "create database $DB" >/dev/null 2>&1
"${PSQL[@]}" -d "$DB" -f tests/sql/supabase_stub.sql >/dev/null
"${PSQL[@]}" -d "$DB" -f supabase_schema.sql 2>/dev/null
"${PSQL[@]}" -d "$DB" -f supabase_schema.sql 2>/dev/null
echo "OK  supabase_schema.sql aplicado dos veces sin errores"
"${PSQL[@]}" -d "$DB" -At -f tests/sql/test_rls_f03.sql 2>&1 | grep -E "OK|FALL|ERROR" | sed 's/^NOTICE:  //'
"${PSQL[@]}" -d postgres -c "drop database $DB" >/dev/null
