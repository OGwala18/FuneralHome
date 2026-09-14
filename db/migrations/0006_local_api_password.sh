#!/bin/bash
# 0006 - LOCAL DEVELOPMENT ONLY. Sets the password for the induduzo_api role.
#
# 0005_api_role.sql creates that role as NOLOGIN and deliberately does not set a
# password: a credential must never live in migration history. On a managed host
# you set it once out of band from your secret store.
#
# Locally that would mean a manual step before the stack works, so this script
# reads the throwaway dev password from the environment and applies it. The
# migration runner (db/migrate.py) SKIPS .sh files, so this never runs against
# Supabase, Railway or any other managed Postgres.
set -euo pipefail

if [ -z "${API_DB_PASSWORD:-}" ]; then
  echo "0006: API_DB_PASSWORD not set; leaving induduzo_api as NOLOGIN." >&2
  echo "0006: the API will not be able to connect until a password is set." >&2
  exit 0
fi

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    alter role induduzo_api login password '${API_DB_PASSWORD}';
EOSQL

echo "0006: local password set for induduzo_api."
