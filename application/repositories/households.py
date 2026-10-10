"""Atomic PostgreSQL writes with optimistic household versions and RLS."""
from dataclasses import dataclass
from uuid import UUID

from psycopg.types.json import Jsonb

from application.domain.households import clean_inventory, clean_member, clean_settings
from application.domain.models import Member
from database.connection import AccessDenied, ConcurrentChange, Database, EditorContext


@dataclass(frozen=True)
class HouseholdSnapshot:
    name: str
    version: int
    cuisines: list[str]
    cooking_effort: str | None
    meal_prep: str | None
    busy_days: list[str]
    members: list[Member]
    inventory: list[dict]


class HouseholdRepository:
    def __init__(self, database: Database, context: EditorContext):
        self.database, self.context = database, context

    def read(self) -> HouseholdSnapshot:
        with self.database.transaction(self.context) as conn:
            household = conn.execute("SELECT * FROM menuagent.households WHERE id = %s", (self.context.household_id,)).fetchone()
            if household is None:
                raise AccessDenied("This editor does not have access to the configured household.")
            members = conn.execute("SELECT * FROM menuagent.members WHERE household_id = %s ORDER BY name, id", (self.context.household_id,)).fetchall()
            inventory = conn.execute("SELECT * FROM menuagent.inventory_items WHERE household_id = %s ORDER BY position", (self.context.household_id,)).fetchall()
        return HouseholdSnapshot(household['name'], household['version'], household['cuisines'], household['cooking_effort'], household['meal_prep'], household['busy_days'],
            [Member(str(row['id']), row['name'], row['kind'], row['age_group'], row['targets'], row['dislikes'], row['restrictions']) for row in members],
            [{"Item": row['name'], "Location": row['location'], "Quantity": row['quantity'], "Unit": row['unit'], "Status": row['status']} for row in inventory])

    def _advance(self, conn, expected_version):
        updated = conn.execute("UPDATE menuagent.households SET version = version + 1, updated_at = now() WHERE id = %s AND version = %s RETURNING version",
                               (self.context.household_id, expected_version)).fetchone()
        if updated is None:
            if not conn.execute("SELECT 1 FROM menuagent.households WHERE id = %s", (self.context.household_id,)).fetchone():
                raise AccessDenied("This editor does not have access to the configured household.")
            raise ConcurrentChange("This household changed in another session. Reload saved data before retrying.")
        return updated['version']

    def save_member(self, member: Member, expected_version: int):
        member = clean_member(member)
        member_id = str(UUID(member.id))
        with self.database.transaction(self.context) as conn:
            version = self._advance(conn, expected_version)
            conn.execute("""INSERT INTO menuagent.members (household_id, id, name, kind, age_group, targets, dislikes, restrictions)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (household_id, id) DO UPDATE SET name = EXCLUDED.name, kind = EXCLUDED.kind,
                    age_group = EXCLUDED.age_group, targets = EXCLUDED.targets, dislikes = EXCLUDED.dislikes, restrictions = EXCLUDED.restrictions""",
                (self.context.household_id, member_id, member.name, member.kind, member.age_group,
                 Jsonb(member.targets) if member.targets is not None else None, member.dislikes, member.restrictions))
        return version

    def save_settings(self, cuisines, cooking_effort, meal_prep, busy_days, expected_version: int):
        cuisines, cooking_effort, meal_prep, busy_days = clean_settings(cuisines, cooking_effort, meal_prep, busy_days)
        with self.database.transaction(self.context) as conn:
            version = self._advance(conn, expected_version)
            conn.execute("UPDATE menuagent.households SET cuisines = %s, cooking_effort = %s, meal_prep = %s, busy_days = %s WHERE id = %s",
                         (cuisines, cooking_effort, meal_prep, busy_days, self.context.household_id))
        return version

    def save_inventory(self, rows, expected_version: int):
        cleaned = clean_inventory(rows)
        with self.database.transaction(self.context) as conn:
            version = self._advance(conn, expected_version)
            conn.execute("DELETE FROM menuagent.inventory_items WHERE household_id = %s", (self.context.household_id,))
            for position, row in enumerate(cleaned):
                conn.execute("""INSERT INTO menuagent.inventory_items (household_id, item_key, name, location, quantity, unit, status, position)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (self.context.household_id, row['Item'].casefold(), row['Item'], row['Location'], row['Quantity'], row['Unit'], row['Status'], position))
        return version
