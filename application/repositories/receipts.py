"""Immutable extraction provenance and atomic, once-only purchase confirmation."""
from psycopg.types.json import Jsonb

from application.domain.households import clean_inventory
from application.domain.receipts import clean_extraction, merge_purchases, receipt_hash, validate_hash
from database.connection import AccessDenied


class ReceiptRepository:
    def __init__(self, household_repository):
        self.households = household_repository
        self.database, self.context = household_repository.database, household_repository.context

    def _check_access(self, conn):
        if not conn.execute("SELECT 1 FROM menuagent.households WHERE id = %s", (self.context.household_id,)).fetchone():
            raise AccessDenied("This editor does not have access to the configured household.")

    def _find(self, conn, image_hash):
        row = conn.execute("""SELECT image_hash, model, extraction, reviewed_items, confirmed_at
            FROM menuagent.receipts WHERE household_id = %s AND image_hash = %s""",
            (self.context.household_id, image_hash)).fetchone()
        return dict(row) if row else None

    def find(self, image_hash):
        validate_hash(image_hash)
        with self.database.transaction(self.context) as conn:
            self._check_access(conn)
            return self._find(conn, image_hash)

    def save_extraction(self, image_bytes, result):
        image_hash = receipt_hash(image_bytes)
        document = clean_extraction(result["extraction"])
        if result["mime"] not in ("image/png", "image/jpeg") or not isinstance(result["model"], str) or not 0 < len(result["model"]) <= 150:
            raise ValueError("Invalid receipt source metadata.")
        with self.database.transaction(self.context) as conn:
            self._check_access(conn)
            # Keep the first extraction, including when another session read it.
            conn.execute("""INSERT INTO menuagent.receipts (household_id, image_hash, image_bytes, mime, model, extraction)
                VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                (self.context.household_id, image_hash, image_bytes, result["mime"], result["model"], Jsonb(document)))
            return self._find(conn, image_hash)

    def confirm(self, image_hash, purchases, expected_version):
        validate_hash(image_hash)
        reviewed = clean_inventory(purchases)
        if not reviewed:
            raise ValueError("Keep at least one grocery item before confirming purchases.")
        if any(row["Status"] == "Out" or row["Quantity"] == 0 for row in reviewed):
            raise ValueError("Remove items you did not buy rather than confirming zero or Out purchases.")
        with self.database.transaction(self.context) as conn:
            self._check_access(conn)
            receipt = self._find(conn, image_hash)
            if receipt is None:
                raise ValueError("Read and save this receipt before confirming it.")
            if receipt["confirmed_at"] is not None:
                raise ValueError("This receipt has already been confirmed. Stock was not added again.")
            version = self.households._advance(conn, expected_version)
            existing = conn.execute("""SELECT name AS "Item", location AS "Location", quantity AS "Quantity",
                unit AS "Unit", status AS "Status" FROM menuagent.inventory_items
                WHERE household_id = %s ORDER BY position""", (self.context.household_id,)).fetchall()
            merged = merge_purchases(existing, reviewed)
            self.households._write_inventory(conn, merged)
            conn.execute("""UPDATE menuagent.receipts SET reviewed_items = %s, confirmed_at = now()
                WHERE household_id = %s AND image_hash = %s""", (Jsonb(reviewed), self.context.household_id, image_hash))
        return version, merged
