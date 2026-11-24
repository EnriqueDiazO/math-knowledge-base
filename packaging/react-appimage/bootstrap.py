"""Start the existing independent React backend from a relocatable read-only bundle."""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path


def main():
    """Keep writable data in the existing XDG policy, outside this executable."""
    root = Path(__file__).resolve().parent
    sys.path[:0] = [str(root / "app"), str(root / "vendor")]
    from mathmongo.advanced_reader.launcher import main as launch

    if sys.argv[1:] == ["--bundle-check"]:
        print(
            json.dumps(
                {
                    "python": sys.version.split()[0],
                    "streamlit_available": importlib.util.find_spec("streamlit") is not None,
                    "frontend": (
                        root / "app/mathmongo/advanced_reader/static/advanced_reader/index.html"
                    ).is_file(),
                    "latex_templates": (root / "app/templates_latex/miestilo.sty").is_file(),
                    "mongo_management": "external",
                    "host_tools": {
                        name: bool(shutil.which(name))
                        for name in ("pdflatex", "pdftoppm", "bwrap", "prlimit")
                    },
                }
            )
        )
        return 0
    return launch()


if __name__ == "__main__":
    raise SystemExit(main())
