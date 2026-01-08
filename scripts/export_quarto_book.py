from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

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
        "title: \"Generated (stub)\"\n"
        "---\n\n"
        "Export stub: the exporter ran successfully.\n",
        encoding="utf-8",
    )

    print(f"Wrote: {out}")

if __name__ == "__main__":
    main()
