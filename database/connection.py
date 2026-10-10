"""Short-lived transactions with trusted editor and household context."""
from contextlib import contextmanager
from dataclasses import dataclass, field
from uuid import UUID

import psycopg
from psycopg.rows import dict_row


class AccessDenied(ValueError):
    pass


class ConcurrentChange(ValueError):
    pass


class StorageUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class EditorContext:
    household_id: str
    subject: str

    def __post_init__(self):
        object.__setattr__(self, "household_id", str(UUID(self.household_id)))
        if not self.subject or not self.subject.strip():
            raise ValueError("An authenticated editor identity is required.")


@dataclass(frozen=True)
class Database:
    conninfo: str = field(repr=False)

    @contextmanager
    def transaction(self, context: EditorContext):
        try:
            with psycopg.connect(self.conninfo, row_factory=dict_row, connect_timeout=5) as conn:
                conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                role = conn.execute("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user").fetchone()
                if role['rolsuper'] or role['rolbypassrls']:
                    raise AccessDenied("Configure an application database role without superuser or RLS bypass privileges.")
                conn.execute("SELECT set_config('menuagent.household_id', %s, true), set_config('menuagent.editor_subject', %s, true)",
                             (context.household_id, context.subject))
                yield conn
        except psycopg.errors.SerializationFailure:
            raise ConcurrentChange("This household changed in another session. Reload saved data before retrying.") from None
        except psycopg.Error:
            # Driver messages can contain connection details. Never render them.
            raise StorageUnavailable("The household database is unavailable or needs migrations. Check the server configuration.") from None
