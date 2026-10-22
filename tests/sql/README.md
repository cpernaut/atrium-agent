# Esquema y seguridad en Postgres real

`run.sh` crea una base limpia, carga `supabase_stub.sql` (roles `anon`,
`authenticated`, `auth.uid()` y los permisos por defecto de Supabase), aplica
`supabase_schema.sql` **dos veces** (tiene que poder re-ejecutarse) y corre
`test_rls_f03.sql`, que falla ante cualquier regla de seguridad o integridad rota.

Corre solo en cada PR (job «Esquema y seguridad en Postgres»). A mano:

```bash
PGHOST=localhost PGPORT=5432 PGUSER=postgres PGPASSWORD=... tests/sql/run.sh
```

Para una funcionalidad nueva con tablas, sumar sus chequeos en un
`test_rls_fXX.sql` y agregarlo a `run.sh`.
