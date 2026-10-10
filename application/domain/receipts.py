"""Receipt extraction is untrusted data; reviewed stock remains the authority."""
from hashlib import sha256
from math import isfinite
import re

from application.domain.households import clean_inventory

MAX_IMAGE_BYTES = 8 * 1024 * 1024
EXTRACTION_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["store", "raw_text", "items"],
    "properties": {
        "store": {"type": ["string", "null"]},
        "raw_text": {"type": "string"},
        "items": {"type": "array", "maxItems": 200, "items": {
            "type": "object", "additionalProperties": False,
            "required": ["name", "quantity", "unit", "location", "raw_line", "note"],
            "properties": {
                "name": {"type": "string"},
                "quantity": {"type": ["number", "null"], "minimum": 0},
                "unit": {"type": "string", "enum": ["g", "ml", "each"]},
                "location": {"type": "string", "enum": ["Fridge", "Pantry", "Freezer"]},
                "raw_line": {"type": "string"}, "note": {"type": "string"},
            },
        }},
    },
}


def receipt_hash(image_bytes):
    if not isinstance(image_bytes, bytes) or not 0 < len(image_bytes) <= MAX_IMAGE_BYTES:
        raise ValueError("Upload a PNG or JPEG receipt of up to 8 MB.")
    return sha256(image_bytes).hexdigest()


def clean_extraction(document):
    if not isinstance(document, dict) or set(document) != {"store", "raw_text", "items"}:
        raise ValueError("The model returned an invalid receipt. Try reading the image again.")
    if document["store"] is not None and (not isinstance(document["store"], str) or len(document["store"]) > 300):
        raise ValueError("The model returned an invalid store name.")
    if not isinstance(document["raw_text"], str) or len(document["raw_text"]) > 50000:
        raise ValueError("The model returned invalid receipt text.")
    items = document["items"]
    if not isinstance(items, list) or len(items) > 200:
        raise ValueError("The model returned too many receipt items.")
    cleaned = []
    for item in items:
        if not isinstance(item, dict) or set(item) != {"name", "quantity", "unit", "location", "raw_line", "note"}:
            raise ValueError("The model returned an invalid grocery item.")
        for key, limit in (("name", 160), ("raw_line", 1000), ("note", 1000)):
            if not isinstance(item[key], str) or len(item[key]) > limit or (key == "name" and not item[key].strip()):
                raise ValueError("The model returned an invalid grocery description.")
        quantity = item["quantity"]
        if quantity is not None:
            try:
                valid = not isinstance(quantity, bool) and isinstance(quantity, (int, float)) and isfinite(quantity) and quantity >= 0
            except OverflowError:
                valid = False
            if not valid:
                raise ValueError("The model returned an invalid quantity.")
        row = clean_inventory([{"Item": item["name"], "Quantity": quantity,
                                "Unit": item["unit"], "Location": item["location"]}])[0]
        # Check enums directly: blank model values must not acquire editor defaults.
        if item["unit"] not in ("g", "ml", "each") or item["location"] not in ("Fridge", "Pantry", "Freezer"):
            raise ValueError("The model returned an unsupported unit or storage location.")
        cleaned.append(dict(item, name=row["Item"], quantity=row["Quantity"]))
    return dict(document, items=cleaned)


def extraction_rows(document):
    """Combine repeated lines for review without inventing quantities."""
    return merge_purchases([], [{"Item": i["name"], "Quantity": i["quantity"], "Unit": i["unit"],
                                 "Location": i["location"], "Status": "Available"}
                                for i in clean_extraction(document)["items"]], allow_repeated=True)


def merge_purchases(inventory, purchases, *, allow_repeated=False):
    stock = clean_inventory(inventory)
    rows = ([clean_inventory([row])[0] for row in purchases] if allow_repeated else clean_inventory(purchases))
    by_key = {(r["Item"].casefold(), r["Location"], r["Unit"]): r for r in stock}
    for row in rows:
        key = (row["Item"].casefold(), row["Location"], row["Unit"])
        if key not in by_key:
            stock.append(dict(row))
            by_key[key] = stock[-1]
            continue
        existing = by_key[key]
        old = 0 if existing["Status"] == "Out" else existing["Quantity"]
        new = row["Quantity"]
        existing["Quantity"] = old + new if old is not None and new is not None else None
        if existing["Quantity"] is not None and not isfinite(existing["Quantity"]):
            raise ValueError("Combined stock quantity is too large.")
        # Retain use-soon stock when adding fresh purchases.
        existing["Status"] = "Use soon" if existing["Status"] == "Use soon" else row["Status"]
    return stock


def validate_hash(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError("Invalid receipt identity.")
    return value
