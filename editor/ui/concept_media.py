"""Concept media; extracted without import-time rendering."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from editor.utils.media_assets import ALLOWED_IMAGE_EXTENSIONS
from editor.utils.media_assets import LATEX_IMAGE_EXTENSIONS
from editor.utils.media_assets import detach_media_asset_from_concept
from editor.utils.media_assets import detect_heavy_tikz
from editor.utils.media_assets import get_concept_media_assets
from editor.utils.media_assets import html_image_snippet
from editor.utils.media_assets import latex_includegraphics_snippet
from editor.utils.media_assets import media_path_exists
from editor.utils.media_assets import resolve_media_asset_path
from editor.utils.media_assets import save_media_asset
from mathdatabase.mathmongo import MathMongo


def _media_tags_from_text(raw: str) -> list[str]:
    return [tag.strip() for tag in (raw or "").split(",") if tag.strip()]


def _render_tikz_weight_warnings(latex: str) -> None:
    for warning in detect_heavy_tikz(latex):
        st.warning(warning)


def _render_media_asset_preview(asset: dict) -> None:
    path = Path(asset.get("path") or "")
    actual_path = resolve_media_asset_path(asset)
    suffix = path.suffix.lower()
    if not media_path_exists(asset):
        st.error(f"Imagen faltante: {asset.get('path')}")
        return
    if suffix == ".pdf":
        st.write(f"PDF image asset: `{asset.get('path')}`")
    else:
        st.image(str(actual_path), caption=asset.get("description") or asset.get("filename"))


def _render_concept_media_manager(
    mongo: MathMongo,
    concept_id: str,
    source: str,
    *,
    prefix: str,
    latex_insert_key: str,
    insert_flag_key: str,
) -> list[dict]:
    st.subheader("🖼️ Images")
    st.caption("Use rutas relativas como `media/images/name.png`; evita rutas absolutas.")

    if not concept_id or not source:
        st.info("Define ID y source antes de asociar imágenes.")
        return []

    uploaded_files = st.file_uploader(
        "Upload image assets",
        type=[ext.lstrip(".") for ext in ALLOWED_IMAGE_EXTENSIONS],
        accept_multiple_files=True,
        key=f"{prefix}_media_upload",
    )
    media_description = st.text_input("Image description/caption", key=f"{prefix}_media_description")
    media_tags = st.text_input("Image tags (comma-separated)", key=f"{prefix}_media_tags")

    if st.button("Guardar imágenes", key=f"{prefix}_save_media"):
        if not uploaded_files:
            st.warning("Selecciona al menos una imagen.")
        else:
            saved_assets = []
            for uploaded in uploaded_files:
                try:
                    asset = save_media_asset(
                        mongo,
                        filename=uploaded.name,
                        data=uploaded.getvalue(),
                        mime_type=getattr(uploaded, "type", None),
                        concept_id=concept_id,
                        source=source,
                        tags=_media_tags_from_text(media_tags),
                        description=media_description,
                    )
                    saved_assets.append(asset)
                except Exception as exc:
                    st.error(f"No se pudo guardar {uploaded.name}: {exc}")
            if saved_assets:
                st.success(f"Guardadas {len(saved_assets)} imagen(es).")
                for asset in saved_assets:
                    st.code(latex_includegraphics_snippet(asset, caption=media_description), language="latex")

    assets = get_concept_media_assets(mongo, concept_id, source)
    if not assets:
        st.info("Este concepto todavía no tiene imágenes asociadas.")
        return []

    for asset in assets:
        label = f"{asset.get('filename', 'image')} · {asset.get('path', '')}"
        with st.expander(label, expanded=False):
            _render_media_asset_preview(asset)
            suffix = Path(asset.get("path") or "").suffix.lower()
            if suffix == ".svg":
                st.warning("SVG se puede previsualizar en HTML, pero pdflatex no lo incluye sin conversión.")
            elif suffix not in LATEX_IMAGE_EXTENSIONS:
                st.warning("Este formato puede no compilar con pdflatex.")
            latex_snippet = latex_includegraphics_snippet(
                asset,
                caption=asset.get("description") or asset.get("filename") or "",
            )
            st.code(latex_snippet, language="latex")
            st.code(html_image_snippet(asset), language="html")
            if st.button("Insertar LaTeX", key=f"{prefix}_insert_media_{asset.get('asset_id')}"):
                st.session_state[latex_insert_key] = latex_snippet
                st.session_state[insert_flag_key] = True
                st.rerun()
            delete_unused = st.checkbox(
                "Eliminar archivo si queda sin uso",
                key=f"{prefix}_delete_unused_{asset.get('asset_id')}",
            )
            if st.button("Desasociar imagen", key=f"{prefix}_detach_media_{asset.get('asset_id')}"):
                deleted = detach_media_asset_from_concept(
                    mongo,
                    asset_id=asset.get("asset_id"),
                    concept_id=concept_id,
                    source=source,
                    delete_if_unreferenced=delete_unused,
                )
                if deleted:
                    st.success("Imagen desasociada y archivo eliminado porque no tenía más referencias.")
                else:
                    st.success("Imagen desasociada del concepto.")
                st.rerun()

    return assets
