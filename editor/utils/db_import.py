import json
import zipfile
from pathlib import Path
from typing import Dict
from mathdatabase.mathmongo import MathMongo

def inspect_export_zip(zip_path: Path) -> Dict:
    """
    Inspect a Math Knowledge Base export ZIP.

    Returns a dict with:
    - base_name
    - metadata
    - collections: {collection_name: count}
    """
    if not zipfile.is_zipfile(zip_path):
        raise ValueError("Uploaded file is not a valid ZIP archive")

    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()

        # Detect base directory
        base_dirs = {p.split("/")[0] for p in names if "/" in p}
        if len(base_dirs) != 1:
            raise ValueError("Invalid export format: ambiguous base directory")

        base_name = base_dirs.pop()

        metadata_path = f"{base_name}/metadata.json"
        if metadata_path not in names:
            raise ValueError("metadata.json not found in export")

        metadata = json.loads(zf.read(metadata_path).decode("utf-8"))

        collections = {}
        for name in names:
            if name.startswith(f"{base_name}/") and name.endswith(".json"):
                coll = Path(name).stem
                if coll == "metadata":
                    continue
                docs = json.loads(zf.read(name).decode("utf-8"))
                collections[coll] = len(docs)

    return {
        "base_name": base_name,
        "metadata": metadata,
        "collections": collections,
    }


def import_zip_into_database(zip_path: Path, mongo: MathMongo) -> None:
    """Import a validated export ZIP into an existing MongoDB database.

    Assumes:
    - zip_path has been validated with inspect_export_zip
    - mongo points to a NEW database
    """
    db = mongo.db

    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()

        base_dirs = {p.split("/")[0] for p in names if "/" in p}
        base_dir = base_dirs.pop()

        for name in names:
            if not name.endswith(".json"):
                continue

            coll = Path(name).stem
            if coll == "metadata":
                continue

            docs = json.loads(zf.read(name).decode("utf-8"))
            if docs:
                db[coll].insert_many(docs)