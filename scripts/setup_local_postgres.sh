#!/usr/bin/env sh
set -eu

local_database=${ALGOSHIELD_LOCAL_DATABASE:-algoshield_local}
test_database=${ALGOSHIELD_LOCAL_TEST_DATABASE:-algoshield_test}
python_binary=${ALGOSHIELD_PYTHON:-.venv/bin/python}

validate_database_name() {
    case "$1" in
        ""|*[!A-Za-z0-9_]*)
            echo "database names may contain only letters, numbers and underscores" >&2
            exit 2
            ;;
    esac
}

create_database() {
    database_name=$1
    exists=$(psql -X -d postgres -Atqc \
        "SELECT 1 FROM pg_database WHERE datname = '$database_name'")
    if [ "$exists" != "1" ]; then
        createdb -- "$database_name"
        echo "Created PostgreSQL database: $database_name"
    else
        echo "PostgreSQL database already exists: $database_name"
    fi
}

apply_migrations() {
    database_name=$1
    DATABASE_URL="postgresql:///$database_name" \
        "$python_binary" -m backend.shared.migrate --apply
}

command -v psql >/dev/null 2>&1 || {
    echo "psql is required" >&2
    exit 1
}
command -v createdb >/dev/null 2>&1 || {
    echo "createdb is required" >&2
    exit 1
}
if [ ! -x "$python_binary" ]; then
    echo "Python environment not found at $python_binary" >&2
    exit 1
fi

validate_database_name "$local_database"
validate_database_name "$test_database"
create_database "$local_database"
create_database "$test_database"
apply_migrations "$local_database"
apply_migrations "$test_database"

cat <<EOF
Local PostgreSQL is ready.
Application: DATABASE_URL=postgresql:///$local_database
Tests:       ALGOSHIELD_TEST_DATABASE_URL=postgresql:///$test_database
EOF
