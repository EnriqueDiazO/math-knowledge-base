"""Compile authored LaTeX with no network, host data or writable directory access.

Reuse the canonical runner/log classification. Only six fixed output files are
writable (16 MiB each); the remaining namespace, including /tmp, is read-only.
No unsandboxed fallback is permitted when bubblewrap/prlimit are unavailable.
"""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from exporters_latex.latex_compile import run_latex_command
from exporters_latex.latex_compile import run_latex_until_stable

TEMPLATES = Path(__file__).resolve().parents[1] / "templates_latex"
OUTPUTS = ("main.pdf", "main.log", "main.aux", "main.out", "main.toc", "preview.png")
READ_ONLY = (
    "/usr",
    "/lib",
    "/lib64",
    "/etc/ld.so.cache",
    "/etc/texmf",
    "/var/lib/texmf",
    "/var/cache/fontconfig",
)


@dataclass(frozen=True)
class CompiledDocument:
    """Only valid output bytes leave the temporary namespace."""

    status: str
    message: str
    pdf: bytes = b""
    png: bytes = b""
    diagnostic: str = ""


def _command(inputs: Path, outputs: Path, executable: str, arguments: list[str]) -> list[str]:
    """Bound CPU, address space and file size without preexec_fn in server threads."""
    command = [
        "bwrap",
        "--unshare-all",
        "--die-with-parent",
        "--new-session",
        "--cap-drop",
        "ALL",
        "--clearenv",
    ]
    for path in READ_ONLY:
        if Path(path).exists():
            command.extend(["--ro-bind", path, path])
    command.extend(
        [
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--ro-bind",
            str(inputs),
            "/inputs",
            "--ro-bind",
            str(outputs),
            "/work",
            "--ro-bind",
            str(outputs / "empty"),
            "/tmp",
        ]
    )
    for name in OUTPUTS:
        command.extend(["--bind", str(outputs / name), "/work/" + name])
    for key, value in {
        "PATH": "/usr/bin:/bin",
        "TEXINPUTS": "/inputs//:",
        "openin_any": "p",
        "openout_any": "p",
        "TEXMFVAR": "/work/texmf",
        "TEXMFCONFIG": "/work/texmf-config",
    }.items():
        command.extend(["--setenv", key, value])
    return [
        *command,
        "--chdir",
        "/work",
        "--remount-ro",
        "/",
        "/usr/bin/prlimit",
        "--cpu=12",
        "--as=805306368",
        "--fsize=16777216",
        "--nofile=128",
        "--nproc=64",
        "--",
        executable,
        *arguments,
    ]


def compile_document(
    source: str, assets: Mapping[str, bytes] | None = None, *, raster=False
) -> CompiledDocument:
    """Compile a full document, preserving its source outside the disposable job."""
    if any(shutil.which(tool) is None for tool in ("bwrap", "prlimit", "pdflatex")):
        return CompiledDocument(
            "unavailable",
            "La compilación aislada requiere bubblewrap, prlimit y pdflatex. El código se conserva; no se ejecutó una alternativa sin aislamiento.",
        )
    if len(source.encode("utf-8")) > 1_000_000 or "\0" in source:
        return CompiledDocument(
            "invalid",
            "El documento supera el límite de compilación o contiene NUL. Conserva y revisa su fuente.",
        )
    with tempfile.TemporaryDirectory(prefix="mathmongo-tex-") as temporary:
        root = Path(temporary)
        inputs, outputs = root / "inputs", root / "outputs"
        inputs.mkdir()
        outputs.mkdir()
        (outputs / "empty").mkdir()
        for name in OUTPUTS:
            (outputs / name).touch(mode=0o600)
        for template in TEMPLATES.iterdir():
            if (
                template.is_file()
                and not template.is_symlink()
                and template.suffix in {".sty", ".cls"}
            ):
                shutil.copyfile(template, inputs / template.name)
        for name, data in (assets or {}).items():
            relative = Path(name)
            if (
                relative.is_absolute()
                or ".." in relative.parts
                or "\\" in name
                or ":" in name
                or any(ord(char) < 32 for char in name)
                or relative.name == "main.tex"
                or not isinstance(data, bytes)
                or len(data) > 16_777_216
            ):
                return CompiledDocument(
                    "invalid", "Un recurso del documento tiene una ruta no permitida."
                )
            target = inputs / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        tex = inputs / "main.tex"
        tex.write_text(source, encoding="utf-8")
        command = _command(
            inputs,
            outputs,
            "/usr/bin/pdflatex",
            [
                "-no-shell-escape",
                "-interaction=nonstopmode",
                "-halt-on-error",
                "-file-line-error",
                "-output-directory=/work",
                "main.tex",
            ],
        )
        try:
            result = run_latex_until_stable(
                command,
                inputs,
                tex,
                outputs / "main.pdf",
                log_path=outputs / "main.log",
                timeout_seconds=20,
                max_passes=3,
            )
            if result["status"] == "failed":
                return CompiledDocument(
                    "failed",
                    "No se pudo compilar este documento. Conserva el código y revisa las macros, los entornos o recursos indicados.",
                    diagnostic=result["log_excerpt"][-8000:],
                )
            png = b""
            if raster:
                if shutil.which("pdftoppm") is None:
                    return CompiledDocument(
                        "unavailable",
                        "La figura se compiló; falta pdftoppm para producir la vista previa.",
                    )
                converted = run_latex_command(
                    _command(
                        inputs,
                        outputs,
                        "/usr/bin/pdftoppm",
                        [
                            "-singlefile",
                            "-png",
                            "-scale-to",
                            "1600",
                            "/work/main.pdf",
                            "/work/preview",
                        ],
                    ),
                    inputs,
                    tex,
                    timeout_seconds=20,
                )
                png = (outputs / "preview.png").read_bytes()
                if converted.returncode or not png.startswith(b"\x89PNG\r\n\x1a\n"):
                    return CompiledDocument(
                        "failed",
                        "La figura se compiló, pero no se pudo crear su vista previa. El código sigue disponible.",
                    )
            return CompiledDocument(
                "ready",
                "Documento compilado con aislamiento.",
                (outputs / "main.pdf").read_bytes(),
                png,
                result["log_excerpt"][-8000:],
            )
        except (OSError, ValueError, TimeoutError) as error:
            return CompiledDocument(
                "failed",
                "No se confirmó la compilación aislada. El documento original se conserva.",
                diagnostic=str(error)[-4000:],
            )
