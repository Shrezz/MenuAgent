"""Explicit image reading and human confirmation; no automatic stock mutation."""
from datetime import datetime, timezone

from application.domain.households import clean_inventory
from application.domain.receipts import merge_purchases, receipt_hash
from application.repositories.receipts import ReceiptRepository
from integrations.ollama import OllamaReceiptReader


class ReceiptReview:
    def __init__(self, household):
        self.household = household
        self.repository = ReceiptRepository(household.repository) if household.persistent else None
        self.preview = {}

    def find(self, image_hash):
        return self.repository.find(image_hash) if self.repository else self.preview.get(image_hash)

    def read(self, image_bytes):
        image_hash = receipt_hash(image_bytes)
        existing = self.find(image_hash)
        if existing:
            return existing
        result = OllamaReceiptReader().extract(image_bytes)
        if self.repository:
            return self.repository.save_extraction(image_bytes, result)
        record = {"image_hash": image_hash, "extraction": result["extraction"], "model": result["model"],
                  "reviewed_items": None, "confirmed_at": None}
        self.preview[image_hash] = record
        return record

    def confirm(self, image_hash, purchases):
        if self.repository:
            version, inventory = self.repository.confirm(image_hash, purchases, self.household.household_version)
            self.household.inventory = inventory
            self.household.household_version = version
            return
        record = self.find(image_hash)
        if not record or record["confirmed_at"] is not None:
            raise ValueError("Read this receipt first, and confirm it only once.")
        reviewed = clean_inventory(purchases)
        if not reviewed or any(r["Status"] == "Out" or r["Quantity"] == 0 for r in reviewed):
            raise ValueError("Keep the groceries you bought; remove zero or Out items before confirming.")
        inventory = merge_purchases(self.household.inventory, reviewed)
        self.household.save_inventory(inventory)
        record["reviewed_items"] = reviewed
        record["confirmed_at"] = datetime.now(timezone.utc)
