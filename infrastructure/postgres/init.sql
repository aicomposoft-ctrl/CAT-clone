-- Postgres init: grant permissions for cat_user
-- The database and user are created by POSTGRES_USER/POSTGRES_DB env vars.
-- This script runs once on first container start.

GRANT ALL PRIVILEGES ON DATABASE cat_db TO cat_user;
