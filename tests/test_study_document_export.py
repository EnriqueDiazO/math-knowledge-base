"""Real PDF/TEX exports and figure caching on an owned standalone library."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from tests.test_knowledge_map_service import create
from tests.test_study_http import http as _http
from tests.test_study_http import owned_client as _owned_client
from tests.test_study_http import service as _service

owned_client = _owned_client
service = _service
http = _http
BASE = "/api/study/v1"


def test_canonical_visual_body_exports_once_with_real_templates_and_a_compiled_pdf(http, service):
    """Generated visual blocks and protected TikZ remain in the downloadable project."""
    client, _ = http
    body = r"""\begin{context}
\begin{definition}{Idea visual}
Una idea $\frac{1}{2}$.
\begin{remark}{}Una nota anidada.\end{remark}
\end{definition}
\begin{tikzpicture}\draw (0,0)--(1,1);\end{tikzpicture}
\end{context}
"""
    key = service.execute(create(service, titulo="Documento mixto", contenido_latex=body))["key"]
    payload = {"concept_keys": [key, key], "format": "tex"}
    response = client.post(BASE + "/export", json=payload)
    assert response.status_code == 200, response.text
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = archive.namelist()
        raw = next(name for name in names if name.endswith("/content/body.tex"))
        assert archive.read(raw).decode() == body
        main = archive.read(next(name for name in names if name.endswith("/main.tex"))).decode()
        assert r"\usepackage{styles/notes}" in main
        fragments = [name for name in names if "/concepts/" in name and name.endswith(".tex")]
        assert len(fragments) == 1
        assert body in archive.read(fragments[0]).decode()
    pdf = client.post(BASE + "/export", json={**payload, "format": "pdf"})
    assert pdf.status_code == 200, pdf.text
    assert pdf.content.startswith(b"%PDF-") and pdf.headers["content-type"] == "application/pdf"
    assert service.db.latex_documents.find_one({"contenido_latex": body}) is not None


def test_preview_is_explicit_content_scoped_and_reuses_only_compatible_cached_output(
    http, service, tmp_path, monkeypatch
):
    """Preview doesn't publish data, shares cache for equal input and rejects another scope."""
    from mathmongo.study import preview

    monkeypatch.setattr(preview, "get_cache_dir", lambda: tmp_path)
    client, context = http
    before = set(service.db.list_collection_names())
    request = {"source": r"\begin{tikzpicture}\draw (0,0)--(1,1);\end{tikzpicture}"}
    first = client.post(BASE + "/document-previews", json=request).json()
    assert first["state"] == "ready" and first["cached"] is False, first
    repeated = client.post(BASE + "/document-previews", json=request).json()
    assert repeated["preview_id"] == first["preview_id"] and repeated["cached"] is True
    identifier = first["preview_id"]
    preview.DocumentPreviews(context["library_id"]).output(identifier, "png").write_bytes(
        b"interrupted"
    )
    assert client.get(BASE + f"/document-previews/{identifier}/png").status_code == 404
    repaired = client.post(BASE + "/document-previews", json=request).json()
    assert repaired["state"] == "ready" and repaired["cached"] is False
    for extension, magic in (("png", b"\x89PNG\r\n\x1a\n"), ("pdf", b"%PDF-")):
        result = client.get(BASE + f"/document-previews/{identifier}/{extension}")
        assert result.status_code == 200 and result.content.startswith(magic)
        assert (
            client.get(
                BASE + f"/document-previews/{identifier}/{extension}",
                headers={"X-MathMongo-Library": "other"},
            ).status_code
            == 409
        )
    changed = client.post(
        BASE + "/document-previews", json={**request, "macros": r"\newcommand{\figureVersion}{two}"}
    ).json()
    assert changed["preview_id"] != identifier and changed["cached"] is False
    assert set(service.db.list_collection_names()) == before
    assert context["library_id"]


def test_document_api_rejects_missing_selection_unsupported_paths_and_foreign_origin(http, service):
    """No request can turn the document API into arbitrary local file access."""
    client, _ = http
    assert client.post(BASE + "/export", json={}).status_code == 422
    assert (
        client.post(BASE + "/export", json={"concept_keys": ["absent@source"]}).status_code == 409
    )
    assert client.post(BASE + "/export", json={"path": "/etc/passwd"}).status_code == 422
    assert (
        client.post(
            BASE + "/document-previews",
            json={"source": "x"},
            headers={"Origin": "https://outside.invalid"},
        ).status_code
        == 403
    )
    assert client.get(BASE + "/document-previews/not-a-hash/png").status_code == 404
    assert service.db.concepts.count_documents({}) == 0


def test_registered_study_blocks_are_declared_by_the_actual_notes_template():
    """Frontend insertion and PDF prerequisites share the real zero-argument contract."""
    root = Path(__file__).resolve().parents[1]
    blocks = json.loads((root / "editor/ui/document_blocks.json").read_text())
    style = (root / "templates_latex/notes.sty").read_text()
    for name, contract in blocks.items():
        assert (r"\newtcolorbox{" + name + "}") in style
        assert contract["arguments"] == 0 and contract["package"] == "notes"


def test_exporter_preserves_authored_source_without_duplicating_its_existing_heading():
    """Metadata supplies an outer heading only when the body does not already have it."""
    from exporters_latex.unified_document import render_concept_fragment

    body = (
        "\n  " + r"\begin{definition}{Idea}" + "\nTexto con $x$.\n" + r"\end{definition}" + "\n\n"
    )
    rendered = render_concept_fragment(
        {"id": "concept", "source": "source", "titulo": "Idea"}, body
    )
    assert body in rendered
    assert r"\section*{Idea}" not in rendered
    other = render_concept_fragment(
        {"id": "concept", "source": "source", "titulo": "Título exterior"}, body
    )
    assert other.count(r"\section*{Título exterior}") == 1
    assert other.count(r"\begin{definition}{Idea}") == 1


def test_export_application_import_does_not_eagerly_construct_the_server_or_import_streamlit():
    """The public factory remains compatible while service/error imports are independent."""
    import subprocess
    import sys

    code = "\n".join(
        [
            "import sys",
            "from mathmongo.study.document_export import compose_project",
            "assert 'mathmongo.advanced_reader.app' not in sys.modules",
            "from mathmongo.advanced_reader import create_app",
            "assert callable(create_app)",
            "assert 'streamlit' not in sys.modules",
        ]
    )
    subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, timeout=10)


def test_preview_cache_prunes_only_its_old_outputs_and_publishes_no_partial_file(
    tmp_path, monkeypatch
):
    """Disposable resources are bounded without deleting unrelated files or documents."""
    from mathmongo.study import preview

    cache = preview.DocumentPreviews("temporary", root=tmp_path)
    cache.root.mkdir(parents=True)
    old = "a" * 64
    current = "b" * 64
    old_files = [cache.output(old, ext) for ext in ("png", "pdf")]
    retained = {cache.output(current, ext) for ext in ("png", "pdf")}
    for path in [*old_files, *retained]:
        path.write_bytes(b"owned output")
    unrelated = cache.root / "important.tex"
    unrelated.write_text("Keep original")
    monkeypatch.setattr(preview, "CACHE_ENTRIES", 1)
    cache._prune(retained)
    assert all(not path.exists() for path in old_files)
    assert all(path.read_bytes() == b"owned output" for path in retained)
    assert unrelated.read_text() == "Keep original"
    target = cache.output(current, "png")
    before = target.read_bytes()

    def interrupted(*args):
        raise OSError("Publication interrupted")

    monkeypatch.setattr(preview.os, "replace", interrupted)
    import pytest

    with pytest.raises(OSError, match="interrupted"):
        preview.atomic_output(target, b"partial replacement")
    assert target.read_bytes() == before
    assert set(cache.root.iterdir()) == retained | {unrelated}


def test_complete_authored_document_keeps_its_preamble_and_is_not_wrapped_again():
    """A complete historical document and a body fragment use distinct outer contracts."""
    import pytest

    from mathmongo.advanced_reader.document_access import AdvancedReaderError
    from mathmongo.study.document_export import compile_project
    from mathmongo.study.document_export import compose_project

    raw = (
        "% Preambulo propio\n"
        + r"""\documentclass{article}
\usepackage{miestilo}
\newcommand{\keptPreamble}{Preambulo conservado}
\begin{document}
\section*{Mi título}
\keptPreamble
\end{document}
"""
    )
    concept = {"id": "full", "source": "temporary", "titulo": "No duplicar", "contenido_latex": raw}
    bundle = compose_project([concept])
    with zipfile.ZipFile(io.BytesIO(bundle.zip_bytes)) as archive:
        main = archive.read(
            next(name for name in archive.namelist() if name.endswith("/main.tex"))
        ).decode()
        assert main.count(r"\documentclass") == 1
        assert r"\section*{No duplicar}" not in main
        assert r"\newcommand{\keptPreamble}" in main
        assert (
            archive.read(
                next(name for name in archive.namelist() if name.endswith("/content/body.tex"))
            ).decode()
            == raw
        )
    assert compile_project(bundle).status == "ready"
    with pytest.raises(AdvancedReaderError, match="export_preamble"):
        compose_project([concept, {**concept, "id": "other"}])
