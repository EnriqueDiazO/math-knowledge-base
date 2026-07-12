"""Regression tests for mutable-path guards at residual XDG writers."""

# ruff: noqa: D103

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

from editor import interactive_graph
from editor import pdf_export
from exporters_latex import latex_validation
from exporters_latex.unified_document import copy_latex_styles
from scripts import install_cuaderno_mode

sys.modules.setdefault("pdf_export", pdf_export)
from editor import cuaderno_page  # noqa: E402


def _unexpected_write(*args, **kwargs):
    raise AssertionError("writer ran before its mutable path was validated")


def test_interactive_graph_rejects_symlinked_runtime_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    runtime_alias = tmp_path / "graph-runtime"
    runtime_alias.symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(interactive_graph, "get_graph_runtime_dir", lambda: runtime_alias)

    with pytest.raises(ValueError, match="Symbolic links"):
        interactive_graph.InteractiveGraphManager(object())

    assert list(outside.iterdir()) == []


def test_interactive_graph_rejects_symlinked_html_leaf(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = tmp_path / "graph-runtime"
    monkeypatch.setattr(interactive_graph, "get_graph_runtime_dir", lambda: runtime)
    monkeypatch.setattr(interactive_graph.st, "info", lambda *args, **kwargs: None)
    manager = interactive_graph.InteractiveGraphManager(object())
    outside = tmp_path / "outside.html"
    outside.write_text("must survive", encoding="utf-8")
    html_leaf = runtime / "fallback_graph_0_0.html"
    html_leaf.symlink_to(outside)

    with pytest.raises(ValueError, match="Symbolic links"):
        manager.build_interactive_graph([], [])

    assert outside.read_text(encoding="utf-8") == "must survive"


def test_interactive_graph_cleanup_rejects_a_symlinked_html_leaf(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = tmp_path / "graph-runtime"
    monkeypatch.setattr(interactive_graph, "get_graph_runtime_dir", lambda: runtime)
    warnings: list[str] = []
    monkeypatch.setattr(interactive_graph.st, "warning", warnings.append)
    manager = interactive_graph.InteractiveGraphManager(object())
    outside = tmp_path / "outside.html"
    outside.write_text("must survive", encoding="utf-8")
    link = runtime / "linked.html"
    link.symlink_to(outside)

    manager.cleanup_temp_files()

    assert warnings and "Symbolic links" in warnings[0]
    assert link.is_symlink()
    assert outside.read_text(encoding="utf-8") == "must survive"


def test_editor_streamlit_backup_and_import_staging_are_guarded() -> None:
    source = (Path(__file__).resolve().parents[1] / "editor/editor_streamlit.py").read_text(
        encoding="utf-8"
    )

    backup_guard = source.index("out_dir = validate_mutable_path(get_backups_dir())")
    backup_mkdir = source.index("out_dir.mkdir(", backup_guard)
    backup_export = source.index("export_database_to_zip(db, out_dir)", backup_mkdir)
    assert backup_guard < backup_mkdir < backup_export

    runtime_guard = source.index("runtime_root = validate_mutable_path(get_runtime_dir())")
    import_guard = source.index("import_runtime = validate_mutable_path(", runtime_guard)
    import_mkdir = source.index("import_runtime.mkdir(", import_guard)
    leaf_guard = source.index("tmp_path = validate_mutable_path(", import_mkdir)
    write_open = source.index("upload_descriptor = os.open(", leaf_guard)
    assert runtime_guard < import_guard < import_mkdir < leaf_guard < write_open

    protected_guard = source.index("if new_db_name.casefold()", write_open)
    mongo_constructor = source.index("MathMongo(db_name=new_db_name)", protected_guard)
    assert protected_guard < mongo_constructor

    preflight_guard = source.index("latex_runtime = validate_mutable_path(get_latex_runtime_dir())")
    preflight_mkdir = source.index("latex_runtime.mkdir(", preflight_guard)
    preflight_temp = source.index("tempfile.TemporaryDirectory(", preflight_mkdir)
    assert preflight_guard < preflight_mkdir < preflight_temp


def test_cuaderno_install_rejects_a_symlinked_media_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outside = tmp_path / "outside-media"
    outside.mkdir()
    alias = tmp_path / "media"
    alias.symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(install_cuaderno_mode, "LOCAL_MEDIA_ROOT", alias)
    monkeypatch.setattr(
        install_cuaderno_mode,
        "LOCAL_MEDIA_IMAGES_DIR",
        alias / "images",
    )

    with pytest.raises(ValueError, match="Symbolic links"):
        install_cuaderno_mode._ensure_media_directories()

    assert list(outside.iterdir()) == []


@pytest.mark.parametrize("symlink_location", ("directory", "leaf"))
def test_promoted_fragment_preview_rejects_symlinked_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    symlink_location: str,
) -> None:
    preview_root = tmp_path / "pdf-preview"
    preview_root.mkdir()
    promoted_dir = preview_root / "promoted_fragments"
    outside_dir = tmp_path / "outside-dir"
    outside_dir.mkdir()
    outside_file = tmp_path / "outside.pdf"
    outside_file.write_bytes(b"must survive")
    fragment = r"x^2"
    safe_id = "promote_preview_" + hashlib.sha256(fragment.encode()).hexdigest()[:16]

    if symlink_location == "directory":
        promoted_dir.symlink_to(outside_dir, target_is_directory=True)
    else:
        promoted_dir.mkdir()
        (promoted_dir / f"mathkb_{safe_id}.pdf").symlink_to(outside_file)

    monkeypatch.setattr(cuaderno_page, "get_pdf_preview_dir", lambda: preview_root)
    monkeypatch.setattr(
        cuaderno_page,
        "generar_pdf_nota_latex_result",
        _unexpected_write,
    )

    with pytest.raises(ValueError, match="Symbolic links"):
        cuaderno_page._generate_promoted_fragment_pdf_payload({}, fragment)

    assert outside_file.read_bytes() == b"must survive"
    assert list(outside_dir.iterdir()) == []


def test_pdf_export_rejects_symlinked_latex_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outside = tmp_path / "outside-runtime"
    outside.mkdir()
    runtime_alias = tmp_path / "latex-runtime"
    runtime_alias.symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(pdf_export, "get_latex_runtime_dir", lambda: runtime_alias)

    with pytest.raises(ValueError, match="Symbolic links"):
        pdf_export._generar_pdf_desde_latex_temporal(
            latex_content="x",
            safe_id="safe",
            temp_prefix="guard_",
            final_pdf=tmp_path / "final.pdf",
        )

    assert list(outside.iterdir()) == []


def test_note_chktex_build_rejects_symlinked_build_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = tmp_path / "latex-runtime"
    runtime.mkdir()
    outside = tmp_path / "outside-build"
    outside.mkdir()
    build_alias = runtime / "note_analysis"
    build_alias.symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(pdf_export, "get_latex_runtime_dir", lambda: runtime)
    monkeypatch.setattr(pdf_export, "EXPORTED_NOTES_BUILD_DIR", build_alias)
    monkeypatch.setattr(
        pdf_export,
        "generar_tex_nota_latex_info",
        lambda *args, **kwargs: {"latex": "x", "source_map": {}},
    )
    monkeypatch.setattr(pdf_export, "run_chktex_analysis", _unexpected_write)

    with pytest.raises(ValueError, match="Symbolic links"):
        pdf_export.analizar_tex_nota_latex_con_chktex({"_id": "note"})

    assert list(outside.iterdir()) == []


def test_pdf_copy_rejects_symlinked_final_leaf(tmp_path: Path) -> None:
    source = tmp_path / "compiled.pdf"
    source.write_bytes(b"compiled")
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(b"must survive")
    final_pdf = tmp_path / "exports/final.pdf"
    final_pdf.parent.mkdir()
    final_pdf.symlink_to(outside)

    with pytest.raises(ValueError, match="Symbolic links"):
        pdf_export._copy_pdf_to_final_path(source, final_pdf)

    assert outside.read_bytes() == b"must survive"


def test_latex_validation_rejects_a_symlinked_tex_leaf(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    outside = tmp_path / "outside.tex"
    outside.write_text("must survive", encoding="utf-8")
    (work_dir / "fragment_test.tex").symlink_to(outside)
    monkeypatch.setattr(latex_validation, "copy_latex_styles", lambda *args: [])
    monkeypatch.setattr(latex_validation, "copy_media_tree_for_latex", lambda *args: None)

    with pytest.raises(ValueError, match="Symbolic links"):
        latex_validation.compile_latex_fragment("x", work_dir=work_dir)

    assert outside.read_text(encoding="utf-8") == "must survive"


def test_latex_styles_reject_a_symlinked_template_ancestor(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    templates = outside / "templates"
    templates.mkdir(parents=True)
    (templates / "private.sty").write_text("PRIVATE", encoding="utf-8")
    alias = tmp_path / "alias"
    alias.symlink_to(outside, target_is_directory=True)
    destination = tmp_path / "build"

    with pytest.raises(ValueError, match="symbolic links"):
        copy_latex_styles(destination, alias / "templates")

    assert not destination.exists()


@pytest.mark.parametrize("operation", ("compile", "validate"))
@pytest.mark.parametrize("path_kind", ("runtime", "work_dir"))
def test_latex_validation_rejects_symlinked_work_roots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    path_kind: str,
) -> None:
    outside = tmp_path / "outside-work"
    outside.mkdir()
    alias = tmp_path / "latex-work"
    alias.symlink_to(outside, target_is_directory=True)
    work_dir = alias if path_kind == "work_dir" else None
    if path_kind == "runtime":
        monkeypatch.setattr(latex_validation, "get_latex_runtime_dir", lambda: alias)
    monkeypatch.setattr(latex_validation, "_write_validation_document", _unexpected_write)

    with pytest.raises(ValueError, match="Symbolic links"):
        if operation == "compile":
            latex_validation.compile_latex_fragment("x", work_dir=work_dir)
        else:
            latex_validation.validate_latex_fragment(
                "x",
                run_compile=False,
                run_linters=True,
                work_dir=work_dir,
            )

    assert list(outside.iterdir()) == []


@pytest.mark.parametrize(
    "writer,suffix",
    (
        (latex_validation.write_json_report, ".json"),
        (latex_validation.write_markdown_report, ".md"),
    ),
)
@pytest.mark.parametrize("symlink_location", ("directory", "leaf"))
def test_latex_reports_reject_symlinked_destinations(
    tmp_path: Path,
    writer,
    suffix: str,
    symlink_location: str,
) -> None:
    outside_dir = tmp_path / "outside-reports"
    outside_dir.mkdir()
    outside_file = tmp_path / f"outside{suffix}"
    outside_file.write_text("must survive", encoding="utf-8")
    reports_dir = tmp_path / "reports"

    if symlink_location == "directory":
        reports_dir.symlink_to(outside_dir, target_is_directory=True)
    else:
        reports_dir.mkdir()
        (reports_dir / f"audit{suffix}").symlink_to(outside_file)

    with pytest.raises(ValueError, match="Symbolic links"):
        writer({"source": "audit", "results": []}, reports_dir / f"audit{suffix}")

    assert outside_file.read_text(encoding="utf-8") == "must survive"
    assert list(outside_dir.iterdir()) == []
