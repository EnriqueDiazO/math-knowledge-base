"""Read only the media referenced by a saved academic note in the active library."""

from importlib import import_module

from editor.cornell.media import _assets_by_id_from_db
from editor.cornell.media import _safe_asset_source_path
from mathmongo.advanced_reader.document_access import AdvancedReaderError

MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".pdf": "application/pdf",
    ".svg": "image/svg+xml",
}


class NoteImages:
    """Reuse canonical reference discovery and path guards, without writes or arbitrary paths."""

    def __init__(self, notes, identity):
        """Bind one existing note and its validated family, not a general media browser."""
        self.notes = notes
        self.note = notes.opened(identity)
        media = import_module("editor." + notes.spec.family + ".media")
        self.document = notes.parse(self.note[notes.spec.family])
        self.ids = getattr(media, notes.spec.family + "_document_image_ids")(self.document)
        self.assets = _assets_by_id_from_db(notes.db, self.ids)

    def path(self, asset_id):
        """Reject resources outside this note before resolving any file."""
        if asset_id not in self.ids:
            raise AdvancedReaderError(
                "note_image_missing", "Esta imagen no pertenece a la nota abierta.", status_code=404
            )
        try:
            return _safe_asset_source_path(
                self.assets.get(asset_id, {}), allowed_extensions=set(MIME_TYPES)
            )
        except (OSError, ValueError):
            raise AdvancedReaderError(
                "note_image_missing",
                "No se encuentra el archivo de esta imagen. Vuelve a asociarlo desde las imágenes de la nota y reintenta.",
                status_code=404,
            ) from None

    def listing(self):
        """Return names and availability without embedding paths or image bytes in the note JSON."""
        images = []
        for asset_id in self.ids:
            asset = self.assets.get(asset_id, {})
            state = "ready"
            try:
                self.path(asset_id)
            except AdvancedReaderError:
                state = "missing"
            images.append(
                {
                    "asset_id": asset_id,
                    "name": asset.get("original_filename")
                    or asset.get("filename")
                    or "Imagen sin nombre",
                    "state": state,
                    "watermark": asset_id == self.document.watermark.image_id,
                }
            )
        return {"images": images}
