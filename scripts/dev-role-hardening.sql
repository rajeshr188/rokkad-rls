-- Local development role-hardening script for PostgreSQL RLS foundation.
-- Run as a superuser or schema owner role (NOT as runtime app role).
-- Example:
--   psql -h 127.0.0.1 -p 5432 -U postgres -d rls_rokkad -v migration_role=rls_rokkad_migration_owner -v runtime_role=rls_rokkad_user -f scripts/dev-role-hardening.sql

\set ON_ERROR_STOP on

-- Expected psql variables:
--   :migration_role
--   :runtime_role

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'migration_role') THEN
        EXECUTE format('CREATE ROLE %I LOGIN', :'migration_role');
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'runtime_role') THEN
        RAISE EXCEPTION 'Runtime role % does not exist', :'runtime_role';
    END IF;
END $$;

DO $$
BEGIN
    -- Runtime role must never bypass RLS.
    EXECUTE format('ALTER ROLE %I NOBYPASSRLS', :'runtime_role');

    -- Allow runtime role to SET ROLE migration role for migrations when needed.
    EXECUTE format('GRANT %I TO %I', :'migration_role', :'runtime_role');
END $$;

-- Transfer ownership of tenant tables to migration role.
-- Discovery rule: public base tables that have workspace_id and RLS enabled.
DO $$
DECLARE
    t text;
BEGIN
    FOR t IN
        SELECT c.relname
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_attribute a ON a.attrelid = c.oid
        WHERE c.relkind = 'r'
          AND n.nspname = 'public'
          AND c.relrowsecurity
          AND a.attname = 'workspace_id'
          AND NOT a.attisdropped
    LOOP
        EXECUTE format('ALTER TABLE IF EXISTS public.%I OWNER TO %I', t, :'migration_role');
    END LOOP;
END $$;

DO $$
BEGIN
    -- Runtime DML grants.
    EXECUTE format('GRANT USAGE ON SCHEMA public TO %I', :'runtime_role');
    EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO %I', :'runtime_role');
    EXECUTE format('GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO %I', :'runtime_role');

    -- Future grants for tables/sequences created by migration role.
    EXECUTE format(
        'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO %I',
        :'migration_role', :'runtime_role'
    );
    EXECUTE format(
        'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO %I',
        :'migration_role', :'runtime_role'
    );
END $$;

-- Verification output.
SELECT rolname, rolcanlogin, rolbypassrls
FROM pg_roles
WHERE rolname IN (:'migration_role', :'runtime_role')
ORDER BY rolname;

SELECT c.relname AS table_name, pg_get_userbyid(c.relowner) AS owner
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_attribute a ON a.attrelid = c.oid
WHERE c.relkind = 'r'
  AND n.nspname = 'public'
    AND c.relrowsecurity
    AND a.attname = 'workspace_id'
    AND NOT a.attisdropped
ORDER BY c.relname;
