"""Regression tests for residual cwd/package-tree write hazards found in the L2 audit."""

# ruff: noqa: D103

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from exporters_latex.exportadorlatex import ExportadorLatex
from exporters_latex.unified_document import export_unified_document_with_inputs
from exporters_quarto.quarto_exporter import QuartoBookExporter
from parsers.markdownparser import MarkdownParser


def test_legacy_tool_imports_are_side_effect_free(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[1]
    working = tmp_path / "empty cwd"
    working.mkdir()
    environment = os.environ.copy()
    environment.update(
        {
            "HOME": str(tmp_path / "home"),
            "XDG_CONFIG_HOME": str(tmp_path / "config"),
            "XDG_DATA_HOME": str(tmp_path / "data"),
            "XDG_CACHE_HOME": str(tmp_path / "cache"),
            "XDG_STATE_HOME": str(tmp_path / "state"),
            "PYTHONPATH": str(project_root),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    code = (
        "import exporters_latex.actualizar_quarto_yml; "
        "import exporters_latex.exportar_qmd_desde_mongo; "
        "import scripts.export_quarto_book; "
        "import scripts.export_quarto_from_mongo; "
        "import scripts.test_cornell_renderer"
    )
    project_python = project_root / "mathdbmongo/bin/python"
    executable = str(project_python) if project_python.exists() else sys.executable

    result = subprocess.run(
        [executable, "-c", code],
        cwd=working,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert list(working.iterdir()) == []
    for name in ("config", "data", "cache", "state"):
        assert not (tmp_path / name).exists()


def test_relative_legacy_outputs_resolve_against_home(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home with spaces"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg-data"))

    parser = MarkdownParser()
    assert Path(parser.carpeta_salida) == tmp_path / "xdg-data/mathmongo/user_templates/plantillas"

    result = export_unified_document_with_inputs(
        "Audit",
        [],
        output_dir="relative-export",
    )
    assert result.output_dir == home / "relative-export/Audit"


def test_single_concept_relative_export_never_uses_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    captured: list[Path] = []
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr("exporters_latex.exportadorlatex.os.makedirs", lambda path, **kwargs: captured.append(Path(path)))
    monkeypatch.setattr(ExportadorLatex, "_copiar_plantillas", lambda self, path: None)
    monkeypatch.setattr("exporters_latex.exportadorlatex.copy_media_tree_for_latex", lambda path: None)
    monkeypatch.setattr(ExportadorLatex, "_escribir_tex", lambda *args: None)
    monkeypatch.setattr(
        "exporters_latex.exportadorlatex.run_latex_until_stable",
        lambda *args, **kwargs: {"status": "success", "passes": 1, "returncode": 0},
    )

    ExportadorLatex().exportar_concepto(
        {"titulo": "Audit"},
        r"x=1",
        salida="relative-concepts",
    )

    assert captured == [home / "relative-concepts"]


def test_quarto_force_replaces_only_owned_contained_builds(tmp_path: Path) -> None:
    template = tmp_path / "template"
    template.mkdir()
    (template / "index.qmd").write_text("template", encoding="utf-8")
    exports = tmp_path / "exports"
    build = exports / "quarto"
    exporter = QuartoBookExporter(template, build, allowed_root=exports)

    exporter.prepare_build()
    assert (build / exporter.BUILD_MARKER).is_file()
    (build / "generated.txt").write_text("old", encoding="utf-8")
    exporter.prepare_build(force=True)
    assert not (build / "generated.txt").exists()

    unrelated = exports / "unrelated"
    unrelated.mkdir()
    keep = unrelated / "keep.txt"
    keep.write_text("keep", encoding="utf-8")
    with pytest.raises(ValueError, match="not owned"):
        QuartoBookExporter(template, unrelated, allowed_root=exports).prepare_build(force=True)
    assert keep.read_text(encoding="utf-8") == "keep"


def test_quarto_rejects_symlink_escape_and_package_tree(
    tmp_path: Path,
) -> None:
    template = tmp_path / "template"
    template.mkdir()
    (template / "index.qmd").write_text("template", encoding="utf-8")
    exports = tmp_path / "exports"
    exports.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    escaped = exports / "quarto"
    escaped.symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="symlink"):
        QuartoBookExporter(template, escaped, allowed_root=exports).prepare_build()

    real_nested_root = tmp_path / "real-nested-root"
    real_nested_root.mkdir()
    nested_alias = exports / "nested-alias"
    nested_alias.symlink_to(real_nested_root, target_is_directory=True)
    with pytest.raises(ValueError, match="Symbolic links"):
        QuartoBookExporter(
            template,
            nested_alias / "quarto",
            allowed_root=exports,
        ).prepare_build()
    assert list(real_nested_root.iterdir()) == []

    project_root = Path(__file__).resolve().parents[1]
    with pytest.raises(ValueError, match="installed MathMongo package"):
        QuartoBookExporter(template, project_root / "templates_latex").prepare_build()


def test_quarto_rejects_symlinks_inside_a_template(tmp_path: Path) -> None:
    template = tmp_path / "template"
    template.mkdir()
    outside = tmp_path / "outside.qmd"
    outside.write_text("private", encoding="utf-8")
    (template / "linked.qmd").symlink_to(outside)
    exports = tmp_path / "exports"

    with pytest.raises(ValueError, match="symbolic links"):
        QuartoBookExporter(template, exports / "quarto", allowed_root=exports).prepare_build()

    assert not exports.exists()


def test_quarto_rejects_a_symlinked_ownership_marker(tmp_path: Path) -> None:
    template = tmp_path / "template"
    template.mkdir()
    (template / "index.qmd").write_text("template", encoding="utf-8")
    exports = tmp_path / "exports"
    build = exports / "quarto"
    build.mkdir(parents=True)
    user_file = build / "user.txt"
    user_file.write_text("keep", encoding="utf-8")
    external_marker = tmp_path / "external-marker"
    external_marker.write_text("mathmongo-quarto-v1\n", encoding="utf-8")
    (build / QuartoBookExporter.BUILD_MARKER).symlink_to(external_marker)

    with pytest.raises(ValueError, match="Symbolic links"):
        QuartoBookExporter(template, build, allowed_root=exports).prepare_build(force=True)

    assert user_file.read_text(encoding="utf-8") == "keep"
    assert external_marker.read_text(encoding="utf-8") == "mathmongo-quarto-v1\n"


def test_quarto_copies_a_read_only_installed_template_to_a_mutable_build(
    tmp_path: Path,
) -> None:
    template = tmp_path / "installed-template"
    nested = template / "chapters"
    nested.mkdir(parents=True)
    (template / "index.qmd").write_text("template", encoding="utf-8")
    (nested / "chapter.qmd").write_text("chapter", encoding="utf-8")
    for source_file in template.rglob("*"):
        if source_file.is_file():
            source_file.chmod(0o444)
    nested.chmod(0o555)
    template.chmod(0o555)
    exports = tmp_path / "exports"
    exporter = QuartoBookExporter(template, exports / "quarto", allowed_root=exports)

    try:
        exporter.prepare_build()
        result = exporter.export_concepts([])
    finally:
        for source_file in template.rglob("*"):
            if source_file.is_file():
                source_file.chmod(0o644)
        template.chmod(0o755)
        nested.chmod(0o755)

    assert (result.build_dir / exporter.BUILD_MARKER).is_file()
    assert (result.build_dir / "references.bib").is_file()
    assert result.build_dir.stat().st_mode & 0o777 == 0o700
    assert (result.build_dir / "chapters").stat().st_mode & 0o777 == 0o700
