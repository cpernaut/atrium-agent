-- Minimal stand-in for what Supabase provides, to run supabase_schema.sql on a
-- plain Postgres (see tests/sql/README.md). NOT for production.
do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then
    create role anon nologin;
    create role authenticated nologin;
    create role service_role nologin bypassrls;
  end if;
end $$;

create schema auth;
create table auth.users (id uuid primary key, email text);
create function auth.uid() returns uuid language sql stable as $$
  select nullif(current_setting('request.jwt.claims', true)::json ->> 'sub', '')::uuid
$$;
grant usage on schema auth to anon, authenticated, service_role;
grant execute on function auth.uid() to anon, authenticated, service_role;
grant references on auth.users to anon, authenticated, service_role;

-- Supabase's default grants: RLS is what actually protects the tables.
grant usage on schema public to anon, authenticated, service_role;
alter default privileges in schema public grant all on tables to anon, authenticated, service_role;
alter default privileges in schema public grant all on sequences to anon, authenticated, service_role;

insert into auth.users values
  ('00000000-0000-0000-0000-00000000000a', 'a@atrium.test'),
  ('00000000-0000-0000-0000-00000000000b', 'b@atrium.test');
