-- Two roles, on purpose.
--
--   firebrief      owns the schema and runs migrations (the container's
--                  POSTGRES_USER, a superuser).
--   firebrief_app  is the runtime role. NOSUPERUSER and NOBYPASSRLS, so row
--                  level security actually applies to it. Tests connect as
--                  this role, which is why they can prove the policies work.
--
-- The app refuses to start if it finds itself connected as anything else.

CREATE ROLE firebrief_app LOGIN PASSWORD 'firebrief_app_dev'
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;

CREATE DATABASE firebrief_test OWNER firebrief;

GRANT CONNECT ON DATABASE firebrief_dev TO firebrief_app;
GRANT CONNECT ON DATABASE firebrief_test TO firebrief_app;
