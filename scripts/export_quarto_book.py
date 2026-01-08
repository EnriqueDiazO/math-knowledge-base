from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _relpath(posix_path: Path, base: Path) -> str:
    return posix_path.relative_to(base).as_posix()


def _collect_qmd(output_dir: Path, glob_pattern: str) -> list[str]:
    return sorted(_relpath(p, output_dir) for p in output_dir.glob(glob_pattern) if p.is_file())


def _write_book_quarto_yml(output_dir: Path) -> None:
    """
    Rewrites output_dir/_quarto.yml with an auto-generated chapter list.
    Assumes the skeleton files exist (copied from template).
    """
    # Required skeleton entries (must exist)
    required = [
        "index.qmd",
        "chapters/README.qmd",
        "atlas/README.qmd",
        "atlas/notas/README.qmd",
        "atlas/ejemplos/README.qmd",
        "atlas/contra_ejemplos/README.qmd",
    ]
    for rel in required:
        if not (output_dir / rel).exists():
            raise SystemExit(f"Missing required file in build: {output_dir / rel}")

    # Collect generated pages (exclude README files)
    chapter_pages = [
        p for p in _collect_qmd(output_dir, "chapters/**/*.qmd")
        if p != "chapters/README.qmd"
    ]
    notas_pages = [
        p for p in _collect_qmd(output_dir, "atlas/notas/**/*.qmd")
        if p != "atlas/notas/README.qmd"
    ]
    ejemplos_pages = [
        p for p in _collect_qmd(output_dir, "atlas/ejemplos/**/*.qmd")
        if p != "atlas/ejemplos/README.qmd"
    ]
    contra_pages = [
        p for p in _collect_qmd(output_dir, "atlas/contra_ejemplos/**/*.qmd")
        if p != "atlas/contra_ejemplos/README.qmd"
    ]

    chapters = []
    chapters.append("index.qmd")

    chapters.append("chapters/README.qmd")
    chapters.extend(chapter_pages)

    chapters.append("atlas/README.qmd")

    chapters.append("atlas/notas/README.qmd")
    chapters.extend(notas_pages)

    chapters.append("atlas/ejemplos/README.qmd")
    chapters.extend(ejemplos_pages)

    chapters.append("atlas/contra_ejemplos/README.qmd")
    chapters.extend(contra_pages)

    # Write _quarto.yml (simple YAML, no external deps)
    yml = []
    yml.append("project:")
    yml.append("  type: book")
    yml.append("  output-dir: _book")
    yml.append("")
    yml.append("book:")
    yml.append('  title: "Math Knowledge Base"')
    yml.append('  subtitle: "Exported from MathMongo"')
    yml.append("  chapters:")
    for ch in chapters:
        yml.append(f"    - {ch}")
    yml.append("")
    yml.append("format:")
    yml.append("  html:")
    yml.append("    toc: true")
    yml.append("    number-sections: true")
    yml.append("")

    (output_dir / "_quarto.yml").write_text("\n".join(yml), encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--template", default="quarto_book", help="Template directory to copy from")
    p.add_argument("--output", default="quarto_book_build", help="Build directory to generate into")
    p.add_argument("--force", action="store_true", help="Delete output dir if it exists")
    args = p.parse_args()

    template_dir = (ROOT / args.template).resolve()
    output_dir = (ROOT / args.output).resolve()

    if not template_dir.exists():
        raise SystemExit(f"Template dir not found: {template_dir}")

    if output_dir.exists():
        if not args.force:
            raise SystemExit(f"Output dir exists: {output_dir} (use --force)")
        shutil.rmtree(output_dir)

    # Copy template -> output
    shutil.copytree(template_dir, output_dir)

    # Generate a stub file inside the BUILD (not the template)
    out = output_dir / "chapters" / "generated_stub.qmd"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        "---\n"
        'title: "Generated (stub)"\n'
        "---\n\n"
        "Export stub: the exporter ran successfully.\n",
        encoding="utf-8",
    )
    print(f"Wrote: {out}")

    # Auto-generate the book TOC in the BUILD
    _write_book_quarto_yml(output_dir)
    print(f"Updated: {output_dir / '_quarto.yml'}")


if __name__ == "__main__":
    main()
