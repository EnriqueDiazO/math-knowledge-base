import json
import zipfile
from datetime import datetime
from pathlib import Path

from bson import ObjectId


def mongo_to_json_safe(obj):
    """
    Recursively convert MongoDB-specific types into JSON-serializable forms.

    - ObjectId   -> str
    - datetime   -> ISO 8601 string
    - dict/list  -> recursively processed
    """
    if isinstance(obj, dict):
        return {k: mongo_to_json_safe(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [mongo_to_json_safe(v) for v in obj]
    elif isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, ObjectId):
        return str(obj)
    else:
        return obj


def export_database_to_zip(mongo, out_dir: Path) -> Path:
    """
    Export the entire MongoDB database to a ZIP archive of JSON files.

    - Read-only
    - No schema assumptions
    - JSON-safe normalization (ObjectId, datetime, nested structures)

    Returns the path to the generated ZIP file.
    """
    db = mongo.db

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    base_name = f"mathkb_export_{timestamp}"

    export_dir = out_dir / base_name
    export_dir.mkdir(parents=True, exist_ok=True)

    metadata = {
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "collections": {},
    }

    # Export each collection
    for collection_name in db.list_collection_names():
        raw_docs = list(db[collection_name].find({}))
        metadata["collections"][collection_name] = len(raw_docs)

        # Normalize documents to JSON-safe structures
        docs = [mongo_to_json_safe(doc) for doc in raw_docs]

        with open(export_dir / f"{collection_name}.json", "w", encoding="utf-8") as f:
            json.dump(docs, f, ensure_ascii=False, indent=2)

    # Write metadata
    with open(export_dir / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    # Zip everything
    zip_path = out_dir / f"{base_name}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in export_dir.rglob("*"):
            zf.write(path, arcname=f"{base_name}/{path.name}")

    return zip_path