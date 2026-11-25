"""Stage structured images with native resolvers before generating portable LaTeX."""

from importlib import import_module
from pathlib import Path
from tempfile import TemporaryDirectory

from editor.latex_bundle import LatexBundleAsset


class StructuredNoteResourceError(ValueError):
    """A required academic image could not be resolved from this library."""


def structured_family(note):
    """Keep the two established persisted formats explicit."""
    return {"cornell_math_v1": "cornell", "cpi_v1": "cpi"}.get(note.get("note_format"))


def prepare_structured_note_images(note, *, db=None, assets_by_id=None):
    """Snapshot image bytes using the same path, format and reference guards as Streamlit."""
    family = structured_family(note)
    if family is None:
        return ()
    persistence = import_module("editor." + family + ".persistence")
    media = import_module("editor." + family + ".media")
    document = getattr(persistence, "extract_" + family + "_document")(note)
    prepare = getattr(media, "prepare_" + family + "_image_assets")
    try:
        with TemporaryDirectory(prefix="mathmongo-note-images-") as directory:
            paths = prepare(document, directory, db=db, assets_by_id=assets_by_id)
            images = tuple(
                LatexBundleAsset(
                    data=(Path(directory) / path).read_bytes(),
                    source_path=path,
                    filename=Path(path).name,
                    asset_id=asset_id,
                )
                for asset_id, path in paths.items()
            )
            if family == "cornell":
                from editor.cornell.renderer import HISTORICAL_LINES_IMAGE
                from editor.cornell.renderer import LINES_IMAGE_INCLUDE_PATH

                if HISTORICAL_LINES_IMAGE.is_file() and not HISTORICAL_LINES_IMAGE.is_symlink():
                    images += (
                        LatexBundleAsset(
                            data=HISTORICAL_LINES_IMAGE.read_bytes(),
                            source_path=LINES_IMAGE_INCLUDE_PATH,
                            filename="lineas.png",
                            metadata={"role": "cornell-page-background"},
                        ),
                    )
            return images
    except (OSError, ValueError) as error:
        ids = getattr(media, family + "_content_image_ids")(document)
        raise StructuredNoteResourceError(
            "No se pudieron recuperar imágenes de esta nota. Abre sus imágenes en "
            "Cuaderno, vuelve a asociar el archivo que falta y reintenta la exportación. "
            "Referencias: " + ", ".join(ids)
        ) from error


def structured_image_paths(images):
    """Native renderers consume stable staged paths; the bundle makes them relative."""
    return {asset.asset_id: asset.source_path for asset in images if asset.asset_id}
