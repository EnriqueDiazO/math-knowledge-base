"""Shared portable watermark state, upload, and compact Streamlit controls."""

from __future__ import annotations

import base64
import hashlib
import html
import io
import re
from collections.abc import Mapping
from typing import Any

from PIL import Image
from PIL import UnidentifiedImageError

from editor.cornell.models import CornellWatermark
from editor.utils.media_assets import delete_media_asset_if_unreferenced
from editor.utils.media_assets import media_collection
from editor.utils.media_assets import media_path_exists
from editor.utils.media_assets import resolve_media_asset_path
from editor.utils.media_assets import reusable_media_asset
from editor.utils.media_assets import save_media_asset
from mathkb_config import MAX_IMAGE_UPLOAD_BYTES

DEFAULT_WATERMARK_OPACITY = 0.07
DEFAULT_WATERMARK_SCALE = 0.70
DEFAULT_WATERMARK_POSITION = "center"
DEFAULT_WATERMARK_ALL_PAGES = True
WATERMARK_UPLOAD_TYPES = ("png", "webp")

_TYPE_LABELS = {"image": "Imagen PNG/WebP", "text": "Texto"}
_TYPE_VALUES = {label: value for value, label in _TYPE_LABELS.items()}
_POSITION_LABELS = {
    "center": "Centro",
    "bottom_right": "Inferior derecha",
    "top_right": "Superior derecha",
}
_POSITION_VALUES = {label: value for value, label in _POSITION_LABELS.items()}


def branding_widget_prefix(note_type: str, note_id: Any) -> str:
    """Return a stable widget prefix scoped by note format and note identity."""
    clean_type = re.sub(r"[^a-z0-9_]+", "_", str(note_type or "note").lower()).strip("_")
    identity = str(note_id or "new")
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
    return f"{clean_type}_branding_{digest}"


def branding_key(note_type: str, note_id: Any, field: str) -> str:
    """Return one unique widget/session key for a note branding field."""
    return f"{branding_widget_prefix(note_type, note_id)}_{field}"


def _watermark_defaults(watermark: CornellWatermark) -> dict[str, Any]:
    return {
        "enabled": watermark.enabled,
        "type": _TYPE_LABELS[watermark.type],
        "text": watermark.text,
        "image_id": watermark.image_id,
        "opacity": watermark.opacity,
        "scale": watermark.scale,
        "position": _POSITION_LABELS[watermark.position],
        "all_pages": watermark.all_pages,
    }


def initialize_branding_state(
    state: Any,
    *,
    note_type: str,
    note_id: Any,
    watermark: CornellWatermark,
) -> None:
    """Initialize note-scoped branding keys without overwriting widget values."""
    for field, value in _watermark_defaults(watermark).items():
        state.setdefault(branding_key(note_type, note_id, field), value)


def clear_branding_state(state: Any, *, note_type: str) -> None:
    """Clear stale note-scoped branding widgets and pending in-memory uploads."""
    prefix = f"{note_type}_branding_"
    for key in tuple(state):
        if str(key).startswith(prefix):
            state.pop(key, None)


def sync_branding_state(
    state: Any,
    *,
    note_type: str,
    note_id: Any,
    watermark: CornellWatermark,
) -> None:
    """Replace all branding state when opening, discarding, or creating a note."""
    clear_branding_state(state, note_type=note_type)
    prefix = branding_widget_prefix(note_type, note_id)
    for field, value in _watermark_defaults(watermark).items():
        state[f"{prefix}_{field}"] = value


def watermark_from_state(
    state: Mapping[str, Any],
    *,
    note_type: str,
    note_id: Any,
    fallback: CornellWatermark,
) -> CornellWatermark:
    """Build a validated watermark from one note's isolated draft state."""
    def key(field: str) -> str:
        return branding_key(note_type, note_id, field)
    type_label = str(state.get(key("type"), _TYPE_LABELS[fallback.type]))
    position_label = str(state.get(key("position"), _POSITION_LABELS[fallback.position]))
    return CornellWatermark(
        enabled=bool(state.get(key("enabled"), fallback.enabled)),
        type=_TYPE_VALUES.get(type_label, type_label if type_label in _TYPE_LABELS else "image"),
        text=str(state.get(key("text"), fallback.text) or ""),
        image_id=str(state.get(key("image_id"), fallback.image_id) or ""),
        opacity=float(state.get(key("opacity"), fallback.opacity)),
        scale=float(state.get(key("scale"), fallback.scale)),
        position=_POSITION_VALUES.get(
            position_label,
            position_label if position_label in _POSITION_LABELS else DEFAULT_WATERMARK_POSITION,
        ),
        all_pages=bool(state.get(key("all_pages"), fallback.all_pages)),
    )


def remove_watermark_state(state: Any, note_type: str, note_id: Any) -> None:
    """Disable and detach a watermark in draft state without persistent writes."""
    state[branding_key(note_type, note_id, "enabled")] = False
    state[branding_key(note_type, note_id, "image_id")] = ""
    state[branding_key(note_type, note_id, "text")] = ""
    state.pop(branding_key(note_type, note_id, "pending_upload"), None)


def reset_watermark_state(state: Any, note_type: str, note_id: Any) -> None:
    """Restore safe visual defaults while retaining the selected watermark image."""
    state[branding_key(note_type, note_id, "opacity")] = DEFAULT_WATERMARK_OPACITY
    state[branding_key(note_type, note_id, "scale")] = DEFAULT_WATERMARK_SCALE
    state[branding_key(note_type, note_id, "position")] = _POSITION_LABELS[
        DEFAULT_WATERMARK_POSITION
    ]
    state[branding_key(note_type, note_id, "all_pages")] = DEFAULT_WATERMARK_ALL_PAGES


def normalize_watermark_upload(
    filename: str,
    data: bytes,
    mime_type: str | None = None,
) -> dict[str, Any]:
    """Validate PNG/WebP bytes and normalize WebP to a transparent portable PNG."""
    raw = bytes(data or b"")
    if not raw:
        raise ValueError("La imagen de marca está vacía.")
    if len(raw) > MAX_IMAGE_UPLOAD_BYTES:
        raise ValueError("La imagen de marca excede el tamaño máximo permitido.")
    suffix = str(filename or "").lower().rsplit(".", 1)[-1]
    if suffix not in WATERMARK_UPLOAD_TYPES:
        raise ValueError("La marca de agua debe ser PNG o WebP.")
    try:
        with Image.open(io.BytesIO(raw)) as image:
            detected = str(image.format or "").upper()
            image.load()
            if detected not in {"PNG", "WEBP"}:
                raise ValueError("Los bytes no corresponden a una imagen PNG o WebP.")
            if detected == "WEBP":
                normalized = io.BytesIO()
                image.convert("RGBA").save(normalized, format="PNG", optimize=True)
                raw = normalized.getvalue()
                filename = re.sub(r"(?i)\.webp$", ".png", filename)
                mime_type = "image/png"
            else:
                mime_type = "image/png"
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("No se pudo leer la imagen de marca.") from exc
    return {
        "filename": filename,
        "data": raw,
        "mime_type": mime_type or "image/png",
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
    }


def stage_watermark_upload(
    state: Any,
    *,
    note_type: str,
    note_id: Any,
    filename: str,
    data: bytes,
    mime_type: str | None = None,
) -> dict[str, Any]:
    """Keep a validated upload in session only until the note is saved."""
    pending = normalize_watermark_upload(filename, data, mime_type)
    state[branding_key(note_type, note_id, "pending_upload")] = pending
    state[branding_key(note_type, note_id, "type")] = _TYPE_LABELS["image"]
    state[branding_key(note_type, note_id, "enabled")] = True
    return pending


def pending_watermark_upload(state: Mapping[str, Any], note_type: str, note_id: Any) -> dict | None:
    """Return the staged upload for exactly one note editor identity."""
    pending = state.get(branding_key(note_type, note_id, "pending_upload"))
    return dict(pending) if isinstance(pending, Mapping) else None


def materialize_pending_watermark(
    db: Any,
    state: Any,
    *,
    note_type: str,
    note_id: Any,
) -> tuple[dict[str, Any] | None, bool]:
    """Persist a staged upload during Save, reusing identical bytes when possible."""
    pending = pending_watermark_upload(state, note_type, note_id)
    if pending is None:
        return None, False
    asset = reusable_media_asset(
        db,
        sha256=str(pending["sha256"]),
        size_bytes=int(pending["size_bytes"]),
    )
    created = asset is None
    if asset is None:
        asset = save_media_asset(
            db,
            filename=str(pending["filename"]),
            data=bytes(pending["data"]),
            mime_type=str(pending["mime_type"]),
            tags=[note_type, "watermark"],
            description="Marca de agua de identidad visual",
        )
    state[branding_key(note_type, note_id, "image_id")] = str(asset["asset_id"])
    return dict(asset), created


def finish_pending_watermark(state: Any, *, note_type: str, note_id: Any) -> None:
    """Forget staged bytes after their note and asset references are saved."""
    state.pop(branding_key(note_type, note_id, "pending_upload"), None)


def rollback_materialized_watermark(db: Any, asset: Mapping[str, Any] | None, *, created: bool) -> None:
    """Remove a newly materialized orphan after a failed note save."""
    if created and asset is not None:
        delete_media_asset_if_unreferenced(db, str(asset.get("asset_id") or ""))


def _thumbnail_html(data: bytes, mime_type: str, alt: str) -> str:
    encoded = base64.b64encode(data).decode("ascii")
    safe_alt = html.escape(alt or "Vista previa de la marca de agua", quote=True)
    safe_mime = "image/webp" if mime_type == "image/webp" else "image/png"
    return (
        '<div style="display:inline-flex;padding:10px;border:1px solid #cbd5e1;border-radius:8px;'
        'background-color:#fff;background-image:linear-gradient(45deg,#e5e7eb 25%,transparent 25%),'
        'linear-gradient(-45deg,#e5e7eb 25%,transparent 25%),linear-gradient(45deg,transparent 75%,#e5e7eb 75%),'
        'linear-gradient(-45deg,transparent 75%,#e5e7eb 75%);background-size:16px 16px;'
        'background-position:0 0,0 8px,8px -8px,-8px 0px">'
        f'<img src="data:{safe_mime};base64,{encoded}" alt="{safe_alt}" '
        'style="display:block;max-width:180px;max-height:130px;object-fit:contain"/></div>'
    )


def _existing_asset_preview(db: Any, asset_id: str) -> tuple[bytes, str, str] | None:
    asset = media_collection(db).find_one({"asset_id": asset_id})
    if not isinstance(asset, Mapping) or not media_path_exists(dict(asset)):
        return None
    path = resolve_media_asset_path(dict(asset))
    return (
        path.read_bytes(),
        str(asset.get("mime_type") or "image/png"),
        str(asset.get("description") or asset.get("original_filename") or "Marca de agua"),
    )


def render_watermark_editor(
    db: Any,
    *,
    note_type: str,
    note_id: Any,
    watermark: CornellWatermark,
    on_change: Any,
) -> None:
    """Render compact note-scoped watermark controls without persistent writes."""
    import streamlit as st

    initialize_branding_state(
        st.session_state,
        note_type=note_type,
        note_id=note_id,
        watermark=watermark,
    )
    def key(field: str) -> str:
        return branding_key(note_type, note_id, field)
    with st.expander("Identidad visual / marca de agua", expanded=False):
        st.checkbox("Usar marca de agua", key=key("enabled"), on_change=on_change)
        watermark_type = st.radio(
            "Tipo",
            options=tuple(_TYPE_VALUES),
            horizontal=True,
            key=key("type"),
            on_change=on_change,
        )
        if _TYPE_VALUES.get(str(watermark_type), "image") == "text":
            st.text_input("Texto de marca", key=key("text"), on_change=on_change)
        else:
            uploaded = st.file_uploader(
                "Seleccionar PNG o WebP",
                type=WATERMARK_UPLOAD_TYPES,
                key=key("upload_widget"),
                help="La imagen se guarda únicamente al guardar la nota.",
            )
            if uploaded is not None:
                try:
                    prior = pending_watermark_upload(st.session_state, note_type, note_id)
                    uploaded_sha = hashlib.sha256(uploaded.getvalue()).hexdigest()
                    if prior is None or prior.get("source_sha256") != uploaded_sha:
                        pending = stage_watermark_upload(
                            st.session_state,
                            note_type=note_type,
                            note_id=note_id,
                            filename=uploaded.name,
                            data=uploaded.getvalue(),
                            mime_type=getattr(uploaded, "type", None),
                        )
                        pending["source_sha256"] = uploaded_sha
                        st.session_state[key("pending_upload")] = pending
                        on_change()
                except ValueError as exc:
                    st.error(str(exc))

            preview = pending_watermark_upload(st.session_state, note_type, note_id)
            if preview is not None:
                st.markdown(
                    _thumbnail_html(
                        bytes(preview["data"]),
                        str(preview["mime_type"]),
                        "Vista previa de la nueva marca de agua",
                    ),
                    unsafe_allow_html=True,
                )
                st.caption("Vista previa local; pendiente de guardar.")
            else:
                asset_id = str(st.session_state.get(key("image_id")) or "")
                if asset_id:
                    try:
                        existing_preview = _existing_asset_preview(db, asset_id)
                    except (OSError, ValueError):
                        existing_preview = None
                    if existing_preview is None:
                        st.warning(f"Asset de marca no encontrado: {asset_id}")
                    else:
                        data, mime_type, alt = existing_preview
                        st.markdown(
                            _thumbnail_html(data, mime_type, alt),
                            unsafe_allow_html=True,
                        )
                else:
                    st.caption("Selecciona una imagen transparente para usarla como marca.")

        opacity_col, scale_col, position_col = st.columns(3)
        opacity_col.slider(
            "Opacidad",
            min_value=0.0,
            max_value=1.0,
            step=0.01,
            key=key("opacity"),
            on_change=on_change,
            help="Para marcas discretas se recomienda 0.06–0.09.",
        )
        scale_col.slider(
            "Tamaño",
            min_value=0.05,
            max_value=2.0,
            step=0.01,
            key=key("scale"),
            on_change=on_change,
            help="Relación respecto del ancho de página; se recomienda 0.68–0.74.",
        )
        position_col.selectbox(
            "Posición",
            options=tuple(_POSITION_VALUES),
            key=key("position"),
            on_change=on_change,
        )
        st.checkbox(
            "Aplicar a todas las páginas",
            key=key("all_pages"),
            on_change=on_change,
        )
        remove_col, reset_col = st.columns(2)
        remove_col.button(
            "Quitar marca de agua",
            key=key("remove"),
            on_click=remove_watermark_state,
            args=(st.session_state, note_type, note_id),
        )
        reset_col.button(
            "Restablecer valores",
            key=key("reset"),
            on_click=reset_watermark_state,
            args=(st.session_state, note_type, note_id),
        )


__all__ = [
    "DEFAULT_WATERMARK_ALL_PAGES",
    "DEFAULT_WATERMARK_OPACITY",
    "DEFAULT_WATERMARK_POSITION",
    "DEFAULT_WATERMARK_SCALE",
    "branding_key",
    "branding_widget_prefix",
    "clear_branding_state",
    "finish_pending_watermark",
    "initialize_branding_state",
    "materialize_pending_watermark",
    "normalize_watermark_upload",
    "pending_watermark_upload",
    "remove_watermark_state",
    "render_watermark_editor",
    "reset_watermark_state",
    "rollback_materialized_watermark",
    "stage_watermark_upload",
    "sync_branding_state",
    "watermark_from_state",
]
