"""BSON-aware snapshots shared by application services and repositories."""

import hashlib

from bson import json_util


def digest(value) -> str:
    """Hash exact BSON-aware snapshots, including unknown metadata."""
    return hashlib.sha256(json_util.dumps(value, sort_keys=True).encode()).hexdigest()


def exact_document(document: dict) -> dict:
    """Compare all observed fields, absent fields and BSON types for one record."""
    return {"_id": document["_id"], "$expr": {"$eq": ["$$ROOT", {"$literal": document}]}}
