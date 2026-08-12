"""Pure construction of portable, self-contained LaTeX project bundles."""

from __future__ import annotations

import hashlib
import io
import json
import re
import unicodedata
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from dataclasses import field
from datetime import date
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any

BUNDLE_FORMAT_VERSION = 1
DEFAULT_ENGINE = "pdflatex"
DOWNLOAD_LABEL = "Descargar proyecto TEX (.zip)"
DOWNLOAD_HELP = "Descarga el TEX, estilos, imágenes, macros y diagnósticos como un proyecto LaTeX portátil."
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")
_SENSITIVE_KEY_PARTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "mongodb",
    "mongo_uri",
    "uri",
)
_UNDEFINED_COMMAND_PATTERN = re.compile(
    r"Undefined control sequence\.(?:.{0,160}\n){0,3}?.*?(\\[A-Za-z@]+)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class LatexBundleAsset:
    """One binary asset already recovered by a caller."""

    data: bytes | None
    source_path: str = ""
    filename: str = ""
    mime_type: str | None = None
    asset_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class LatexBundleResult:
    """In-memory ZIP result suitable for a download widget."""

    zip_bytes: bytes
    download_filename: str
    entries: tuple[str, ...]
    warnings: tuple[str, ...]
    missing_assets: tuple[str, ...]


def latex_project_download_options(bundle: LatexBundleResult) -> dict[str, str | bytes]:
    """Return testable Streamlit download parameters for a LaTeX project."""
    return {
        "data": bundle.zip_bytes,
        "file_name": bundle.download_filename,
        "mime": "application/zip",
        "help": DOWNLOAD_HELP,
    }


def _safe_component(value: object, fallback: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or "").strip())
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_value = _CONTROL_CHARACTERS.sub("", ascii_value)
    ascii_value = ascii_value.replace("/", "_").replace("\\", "_")
    ascii_value = re.sub(r"[^A-Za-z0-9._-]+", "_", ascii_value)
    ascii_value = re.sub(r"_+", "_", ascii_value).strip("._-")
    return ascii_value or fallback


def _safe_relative_path(value: object) -> str | None:
    """Reject absolute/control-character/parent-traversal archive names."""
    text = str(value or "").strip().replace("\\", "/")
    if not text or _CONTROL_CHARACTERS.search(text):
        return None
    path = PurePosixPath(text)
    if path.is_absolute() or ".." in path.parts:
        return None
    parts = [_safe_component(part, "file") for part in path.parts if part not in {"", "."}]
    return "/".join(parts) if parts else None


def _portable_reference(value: object, fallback: str = "asset") -> str:
    """Keep metadata useful without retaining an absolute or traversal path."""
    text = str(value or "").replace("\\", "/")
    path = PurePosixPath(text)
    if path.is_absolute() or ".." in path.parts or re.match(r"^[A-Za-z]:/", text):
        return _safe_component(path.name, fallback)
    return text


def _as_bytes(value: str | bytes | bytearray) -> bytes:
    return value.encode("utf-8") if isinstance(value, str) else bytes(value)


def _json_safe(value: Any, *, key: str = "") -> Any:
    """Serialize metadata without credentials, Mongo URIs, or absolute paths."""
    if any(part in key.casefold() for part in _SENSITIVE_KEY_PARTS):
        return None
    if isinstance(value, Mapping):
        output: dict[str, Any] = {}
        for child_key, child_value in value.items():
            safe_value = _json_safe(child_value, key=str(child_key))
            if safe_value is not None:
                output[str(child_key)] = safe_value
        return output
    if isinstance(value, list | tuple | set):
        return [_json_safe(item, key=key) for item in value]
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, bytes):
        return {"type": "bytes", "size": len(value), "sha256": hashlib.sha256(value).hexdigest()}
    if isinstance(value, str):
        if value.startswith(("mongodb://", "mongodb+srv://")):
            return None
        return _portable_reference(value, "value")
    if hasattr(value, "__class__") and value.__class__.__name__ == "ObjectId":
        return str(value)
    if value is None or isinstance(value, str | int | float | bool):
        return value
    return str(value)


def _diagnostic_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace").strip()
    return json.dumps(_json_safe(value), ensure_ascii=False, indent=2, sort_keys=True).strip()


def _undefined_commands(*reports: object) -> tuple[str, ...]:
    found: set[str] = set()
    for report in reports:
        found.update(_UNDEFINED_COMMAND_PATTERN.findall(_diagnostic_text(report)))
    return tuple(sorted(found))


def _summary_text(summary: object) -> str:
    if not isinstance(summary, Mapping):
        return _diagnostic_text(summary)
    fields = (
        ("motor", summary.get("engine") or summary.get("motor") or DEFAULT_ENGINE),
        ("comando", summary.get("command") or ""),
        ("código de retorno", summary.get("returncode", "")),
        ("primera línea fatal", summary.get("first_latex_error") or summary.get("fatal_error") or ""),
        ("líneas reportadas", summary.get("latex_error_line") or summary.get("reported_line") or ""),
        ("PDF generado", "sí" if summary.get("pdf_generated") or summary.get("pdf_path") else "no"),
        ("PDF considerado válido", "sí" if summary.get("pdf_valid") or summary.get("status") in {"success", "success_with_warnings"} else "no"),
    )
    return "\n".join(f"{label}: {value}" for label, value in fields) + "\n"


def _readme_text(title: str, missing: tuple[str, ...], undefined: tuple[str, ...]) -> str:
    missing_lines = "\n".join(f"- `{item}`" for item in missing) or "- Ninguno reportado."
    undefined_lines = "\n".join(f"- `{item}`" for item in undefined) or "- Ninguno reportado."
    return f"""# Proyecto LaTeX portátil: {title}

Este ZIP contiene el documento TEX principal (`main.tex`), el cuerpo original
en `content/body.tex`, estilos propios, imágenes disponibles, metadatos y los
diagnósticos disponibles. El ZIP se genera incluso si falla la compilación PDF.

## Compilar

```bash
latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
```

Como alternativa:

```bash
pdflatex -interaction=nonstopmode main.tex
pdflatex -interaction=nonstopmode main.tex
```

La segunda pasada es necesaria para resolver índices, números de página y
referencias internas. Las bibliografías generadas directamente con
`thebibliography` ya están incorporadas en `main.tex` y no requieren Biber.

No se requiere `--shell-escape`. Agrega macros personales en `user_macros.tex`;
las macros conocidas del proyecto están en `styles/mathmongo-macros.sty`.
Revisa `diagnostics/` si la compilación muestra errores o advertencias.

## Assets faltantes

{missing_lines}

## Comandos no definidos detectados

{undefined_lines}
"""


def _inject_user_macro_input(main_tex: str) -> str:
    instruction = r"\InputIfFileExists{user_macros.tex}{}{}"
    macro_package = r"\usepackage{mathmongo-macros}"
    if macro_package not in main_tex:
        marker = r"\begin{document}"
        if marker in main_tex:
            main_tex = main_tex.replace(marker, macro_package + "\n" + marker, 1)
        else:
            main_tex = main_tex.rstrip() + "\n" + macro_package + "\n"
    if instruction in main_tex:
        return main_tex
    marker = r"\begin{document}"
    if marker in main_tex:
        return main_tex.replace(marker, instruction + "\n" + marker, 1)
    return main_tex.rstrip() + "\n" + instruction + "\n"


def _rewrite_project_style_paths(main_tex: str, style_names: set[str]) -> str:
    """Use paths relative to the bundle root for project-owned style files."""
    rewritten = main_tex
    for name in sorted(style_names, key=len, reverse=True):
        stem = re.escape(PurePosixPath(name).stem)
        rewritten = re.sub(
            rf"(\\usepackage(?:\[[^\]]*\])?\{{){stem}(\}})",
            rf"\1styles/{PurePosixPath(name).stem}\2",
            rewritten,
        )
        if name.endswith(".cls"):
            rewritten = re.sub(
                rf"(\\documentclass(?:\[[^\]]*\])?\{{){stem}(\}})",
                rf"\1styles/{PurePosixPath(name).stem}\2",
                rewritten,
            )
    return rewritten


def _rewrite_style_dependencies(style_text: str, style_names: set[str]) -> str:
    """Make project-owned style dependencies resolve from the bundled styles/ folder."""
    rewritten = style_text
    for name in sorted(style_names, key=len, reverse=True):
        stem = re.escape(PurePosixPath(name).stem)
        for command in ("RequirePackage", "usepackage", "LoadClass"):
            rewritten = re.sub(
                rf"(\\{command}(?:\[[^\]]*\])?\{{){stem}(\}})",
                rf"\1styles/{PurePosixPath(name).stem}\2",
                rewritten,
            )
    return rewritten


def _rewrite_asset_references(text: str, replacements: list[tuple[str, str]]) -> str:
    """Replace source references atomically so filenames do not re-rewrite paths."""
    ordered = sorted(set(replacements), key=lambda item: len(item[0]), reverse=True)
    placeholders: list[tuple[str, str]] = []
    for index, (original, replacement) in enumerate(ordered):
        placeholder = f"@@MATHMONGO_ASSET_{index}@@"
        text = text.replace(original, placeholder)
        placeholders.append((placeholder, replacement))
    for placeholder, replacement in placeholders:
        text = text.replace(placeholder, replacement)
    return text


def _normalize_asset(value: LatexBundleAsset | Mapping[str, Any]) -> LatexBundleAsset:
    if isinstance(value, LatexBundleAsset):
        return value
    data = value.get("data")
    if data is not None and not isinstance(data, bytes | bytearray):
        raise TypeError("LaTeX bundle assets must provide bytes or None for data")
    return LatexBundleAsset(
        data=bytes(data) if data is not None else None,
        source_path=str(value.get("source_path") or value.get("path") or ""),
        filename=str(value.get("filename") or value.get("original_filename") or ""),
        mime_type=str(value.get("mime_type") or "") or None,
        asset_id=str(value.get("asset_id") or "") or None,
        metadata=value.get("metadata") if isinstance(value.get("metadata"), Mapping) else {},
    )


def build_latex_project_bundle(
    *,
    main_tex: str,
    raw_body: str,
    metadata: Mapping[str, Any] | None = None,
    project_styles: Mapping[str, str | bytes | bytearray] | None = None,
    images: tuple[LatexBundleAsset | Mapping[str, Any], ...] | list[LatexBundleAsset | Mapping[str, Any]] = (),
    additional_assets: Mapping[str, str | bytes | bytearray] | None = None,
    bibliography: Mapping[str, str | bytes | bytearray] | str | bytes | bytearray | None = None,
    chktex_report: object | None = None,
    latex_log: object | None = None,
    compilation_summary: object | None = None,
    source_type: str | None = None,
    source_id: str | None = None,
    title: str | None = None,
    expected_engine: str = DEFAULT_ENGINE,
) -> LatexBundleResult:
    """Build a ZIP in memory without compiling LaTeX or consulting a database."""
    safe_title = _safe_component(title or source_id or "documento", "documento")
    root = f"{safe_title}_latex"
    warnings: list[str] = []
    missing_assets: list[str] = []
    style_names: set[str] = set()
    files: dict[str, bytes] = {
        "main.tex": _inject_user_macro_input(str(main_tex)).encode("utf-8"),
        "content/body.tex": str(raw_body).encode("utf-8"),
        "user_macros.tex": (
            "% Agrega aquí macros personales para este documento.\n"
            "% Este archivo se carga de forma opcional desde main.tex.\n"
        ).encode(),
    }

    for name, content in sorted((project_styles or {}).items(), key=lambda item: str(item[0])):
        safe_name = _safe_relative_path(name)
        if safe_name is None or "/" in safe_name:
            warnings.append(f"Estilo omitido por ruta insegura: {name!r}")
            continue
        files[f"styles/{safe_name}"] = _as_bytes(content)
        style_names.add(safe_name)
    for name in style_names:
        path = f"styles/{name}"
        try:
            files[path] = _rewrite_style_dependencies(
                files[path].decode("utf-8"), style_names
            ).encode("utf-8")
        except UnicodeDecodeError:
            warnings.append(f"Estilo no textual conservado sin reescritura: {name}")
    for name, content in sorted((additional_assets or {}).items(), key=lambda item: str(item[0])):
        safe_name = _safe_relative_path(name)
        if safe_name is None:
            warnings.append(f"Asset adicional omitido por ruta insegura: {name!r}")
            continue
        files[safe_name] = _as_bytes(content)
    if bibliography:
        bib_items = bibliography if isinstance(bibliography, Mapping) else {"references.bib": bibliography}
        for name, content in sorted(bib_items.items(), key=lambda item: str(item[0])):
            safe_name = _safe_relative_path(name)
            if safe_name is None or "/" in safe_name:
                warnings.append(f"Bibliografía omitida por ruta insegura: {name!r}")
                continue
            files[f"bibliography/{safe_name}"] = _as_bytes(content)

    normalized_assets = [_normalize_asset(item) for item in images]
    normalized_assets.sort(key=lambda item: (item.filename or item.source_path or "image", item.source_path, item.asset_id or ""))
    seen_names: dict[str, int] = {}
    replacements: list[tuple[str, str]] = []
    asset_metadata: list[dict[str, Any]] = []
    for asset in normalized_assets:
        raw_name = asset.filename or PurePosixPath(asset.source_path.replace("\\", "/")).name or "image"
        safe_name = _safe_component(raw_name, "image")
        stem, dot, suffix = safe_name.rpartition(".")
        base, extension = (stem, f".{suffix}") if dot else (safe_name, "")
        number = seen_names.get(safe_name, 0) + 1
        seen_names[safe_name] = number
        exported_name = safe_name if number == 1 else f"{base}_{number}{extension}"
        destination = f"images/{exported_name}"
        reference = _portable_reference(
            asset.source_path or asset.filename or asset.asset_id or raw_name,
            "asset",
        )
        if not asset.data:
            warnings.append(f"Asset faltante o vacío: {reference}")
            missing_assets.append(reference)
            asset_metadata.append({"asset_id": asset.asset_id, "source_path": reference, "filename": asset.filename, "status": "missing"})
            continue
        files[destination] = asset.data
        replacements.extend((candidate.replace("\\", "/"), destination) for candidate in (asset.source_path, asset.filename) if candidate)
        asset_metadata.append({
            "asset_id": asset.asset_id,
            "source_path": _portable_reference(asset.source_path, "asset"),
            "filename": asset.filename,
            "bundle_path": destination,
            "mime_type": asset.mime_type,
            "size_bytes": len(asset.data),
            "sha256": hashlib.sha256(asset.data).hexdigest(),
            "metadata": _json_safe(asset.metadata),
            "status": "included",
        })
    main_text = _rewrite_project_style_paths(files["main.tex"].decode("utf-8"), style_names)
    main_text = _rewrite_asset_references(main_text, replacements)
    files["main.tex"] = main_text.encode("utf-8")
    for path, content in tuple(files.items()):
        if path in {"main.tex", "content/body.tex"} or not path.endswith(".tex"):
            continue
        text = content.decode("utf-8", errors="replace")
        files[path] = _rewrite_asset_references(text, replacements).encode("utf-8")

    source_metadata = _json_safe(metadata or {})
    if not isinstance(source_metadata, dict):
        source_metadata = {"value": source_metadata}
    source_metadata.update({"title": title or source_metadata.get("title") or "", "source_type": source_type or "", "source_id": source_id or "", "assets": asset_metadata})
    files["metadata/source.json"] = (json.dumps(source_metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")

    chktex_text, latex_log_text, summary_text = _diagnostic_text(chktex_report), _diagnostic_text(latex_log), _summary_text(compilation_summary)
    if chktex_text:
        files["diagnostics/chktex.txt"] = (chktex_text + "\n").encode("utf-8")
    if latex_log_text:
        files["diagnostics/latex.log"] = (latex_log_text + "\n").encode("utf-8")
    if summary_text:
        files["diagnostics/compilation-summary.txt"] = summary_text.encode("utf-8")
    undefined = _undefined_commands(latex_log, compilation_summary)
    if undefined:
        files["diagnostics/undefined-commands.txt"] = ("\n".join(undefined) + "\n").encode("utf-8")
        warnings.append("Comandos no definidos detectados: " + ", ".join(undefined))
    files["README.md"] = _readme_text(str(title or source_id or "documento"), tuple(missing_assets), undefined).encode("utf-8")

    manifest_entries = [{"path": path, "size_bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()} for path, content in sorted(files.items())]
    manifest = {
        "format_version": BUNDLE_FORMAT_VERSION,
        "source_type": source_type or "",
        "source_id": source_id or "",
        "main_file": "main.tex",
        "latex_engine": expected_engine or DEFAULT_ENGINE,
        "files": manifest_entries,
        "missing_assets": missing_assets,
        "warnings": warnings,
        "manifest_note": "manifest.json is excluded from files to avoid a self-referential checksum.",
    }
    files["manifest.json"] = (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for relative_path, content in sorted(files.items()):
            info = zipfile.ZipInfo(f"{root}/{relative_path}", date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content)
    return LatexBundleResult(buffer.getvalue(), f"{root}.zip", tuple(f"{root}/{path}" for path in sorted(files)), tuple(warnings), tuple(missing_assets))


__all__ = [
    "BUNDLE_FORMAT_VERSION",
    "DEFAULT_ENGINE",
    "DOWNLOAD_HELP",
    "DOWNLOAD_LABEL",
    "LatexBundleAsset",
    "LatexBundleResult",
    "build_latex_project_bundle",
    "latex_project_download_options",
]
