"""Administrative migrations and explicit editor provisioning; no UI credentials."""
import argparse
from hashlib import sha256
import os
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
from psycopg import sql

MIGRATIONS = Path(__file__).parent / "migrations"


def migrate(admin_conninfo):
    with psycopg.connect(admin_conninfo) as conn:
        conn.execute("SELECT pg_advisory_xact_lock(617284103)")
        conn.execute("CREATE SCHEMA IF NOT EXISTS menuagent")
        conn.execute("CREATE TABLE IF NOT EXISTS menuagent.schema_migrations (name text PRIMARY KEY, checksum text NOT NULL, applied_at timestamptz NOT NULL DEFAULT now())")
        applied = dict(conn.execute("SELECT name, checksum FROM menuagent.schema_migrations").fetchall())
        for path in sorted(MIGRATIONS.glob("*.sql")):
            content = path.read_bytes()
            checksum = sha256(content).hexdigest()
            if path.name in applied:
                if applied[path.name] != checksum:
                    raise ValueError("An applied migration changed; add a new migration instead.")
                continue
            conn.execute(content.decode("utf-8"), prepare=False)
            conn.execute("INSERT INTO menuagent.schema_migrations (name, checksum) VALUES (%s, %s)", (path.name, checksum))


def grant_app_role(admin_conninfo, role):
    with psycopg.connect(admin_conninfo) as conn:
        info = conn.execute("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = %s", (role,)).fetchone()
        if info is None or any(info):
            raise ValueError("The application role must exist without superuser or RLS bypass privileges.")
        conn.execute(sql.SQL("GRANT USAGE ON SCHEMA menuagent TO {}").format(sql.Identifier(role)))
        conn.execute(sql.SQL("GRANT SELECT, UPDATE ON menuagent.households TO {}").format(sql.Identifier(role)))
        conn.execute(sql.SQL("GRANT SELECT, INSERT, UPDATE, DELETE ON menuagent.members, menuagent.inventory_items TO {}").format(sql.Identifier(role)))
        conn.execute(sql.SQL("GRANT SELECT, INSERT ON menuagent.recipe_versions TO {}").format(sql.Identifier(role)))
        conn.execute(sql.SQL("GRANT SELECT, INSERT, UPDATE ON menuagent.food_sources TO {}").format(sql.Identifier(role)))
        conn.execute(sql.SQL("GRANT SELECT ON menuagent.editor_access TO {}").format(sql.Identifier(role)))


def bootstrap_household(admin_conninfo, household_id, name, editor_subject):
    household_id = str(UUID(household_id))
    if not name.strip() or not editor_subject.strip():
        raise ValueError("A household name and editor subject are required.")
    with psycopg.connect(admin_conninfo) as conn:
        # Administrative provisioning must be able to bypass forced RLS.
        if not conn.execute("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user").fetchone()[0]:
            raise ValueError("Provision households with an administrative role that can bypass RLS.")
        conn.execute("INSERT INTO menuagent.households (id, name) VALUES (%s, %s) ON CONFLICT (id) DO NOTHING", (household_id, name.strip()))
        conn.execute("INSERT INTO menuagent.editor_access (household_id, editor_subject) VALUES (%s, %s) ON CONFLICT DO NOTHING", (household_id, editor_subject))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    migration = sub.add_parser("migrate")
    migration.add_argument("--app-role", required=True)
    bootstrap = sub.add_parser("bootstrap")
    bootstrap.add_argument("--household-id", default=str(uuid4()))
    bootstrap.add_argument("--name", required=True)
    bootstrap.add_argument("--editor-subject", required=True)
    args = parser.parse_args()
    admin = os.environ.get("MENUAGENT_ADMIN_DATABASE_URL")
    if not admin:
        parser.error("Set MENUAGENT_ADMIN_DATABASE_URL in the process environment.")
    try:
        if args.command == "migrate":
            migrate(admin)
            grant_app_role(admin, args.app_role)
            print("Migrations applied and application permissions granted.")
        else:
            bootstrap_household(admin, args.household_id, args.name, args.editor_subject)
            print("Household provisioned:", args.household_id)
    except (psycopg.Error, ValueError) as error:
        # Never print driver exceptions or supplied connection strings.
        parser.exit(1, f"Database administration failed ({type(error).__name__}). Check configuration and privileges.\n")


if __name__ == "__main__":
    main()
