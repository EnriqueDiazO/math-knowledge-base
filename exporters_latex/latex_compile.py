"""Shared helpers for running LaTeX commands with clear diagnostics."""

from __future__ import annotations

import shlex
import shutil
import subprocess
import re
from pathlib import Path
from typing import Sequence

from mathkb_config import LATEX_MAX_PASSES
from mathkb_config import PDF_COMPILE_TIMEOUT_SECONDS


INCLUDEGRAPHICS_RE = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\{([^{}]+)\}")
OUTPUT_WRITTEN_RE = re.compile(r"Output written on .*?\.pdf", re.IGNORECASE | re.DOTALL)
UNDEFINED_REFERENCE_RE = re.compile(r"(?:Reference|Citation) `([^`']+)' undefined", re.IGNORECASE)
WARNING_RE = re.compile(
    r"^(?:LaTeX(?: Font)?|Package [^\n]+|Class [^\n]+|pdfTeX) Warning:.*$",
    re.IGNORECASE | re.MULTILINE,
)
FATAL_ERROR_PATTERNS = (
    re.compile(r"^! LaTeX Error:.*$", re.MULTILINE),
    re.compile(r"^! Package .+ Error:.*$", re.MULTILINE),
    re.compile(r"^! Class .+ Error:.*$", re.MULTILINE),
    re.compile(r"^! Undefined control sequence\\?.*$", re.MULTILINE),
    re.compile(r"^! Emergency stop\\?.*$", re.MULTILINE),
    re.compile(r"^! File `[^']+' not found\\?.*$", re.MULTILINE),
    re.compile(r"^! Missing \$ inserted\\?.*$", re.MULTILINE),
    re.compile(r"^! Extra \\}, or forgotten .*", re.MULTILINE),
    re.compile(r"^Runaway argument\\?.*$", re.MULTILINE),
    re.compile(r"Fatal error occurred", re.IGNORECASE),
    re.compile(r"No output PDF file produced", re.IGNORECASE),
)
RERUN_PATTERNS = (
    "Rerun to get cross-references right",
    "Rerun to get outlines right",
    "Label(s) may have changed",
    "File `.out' has changed",
    "There were undefined references",
)


def command_to_text(command: Sequence[str | Path]) -> str:
    return " ".join(shlex.quote(str(part)) for part in command)


def read_text_tail(path: str | Path, lines: int = 80) -> str:
    path = Path(path)
    if not path.exists():
        return ""
    content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(content[-lines:])


def read_text(path: str | Path) -> str:
    path = Path(path)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def output_tail(stdout: str | None = "", stderr: str | None = "", lines: int = 80) -> str:
    output = "\n".join(part for part in (stdout or "", stderr or "") if part)
    return "\n".join(output.splitlines()[-lines:])


def _dedupe_preserving_order(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        clean = (value or "").strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        result.append(clean)
    return result


def pdf_looks_valid(pdf_path: str | Path) -> bool:
    path = Path(pdf_path)
    if not path.exists() or path.stat().st_size <= 0:
        return False
    try:
        with open(path, "rb") as handle:
            return handle.read(4) == b"%PDF"
    except OSError:
        return False


def extract_latex_warnings(log_text: str) -> list[str]:
    warnings = WARNING_RE.findall(log_text or "")
    return _dedupe_preserving_order(warnings)


def extract_latex_fatal_errors(log_text: str) -> list[str]:
    fatal_errors: list[str] = []
    for pattern in FATAL_ERROR_PATTERNS:
        fatal_errors.extend(match.group(0) for match in pattern.finditer(log_text or ""))
    return _dedupe_preserving_order(fatal_errors)


def extract_undefined_references(log_text: str) -> list[str]:
    return _dedupe_preserving_order(UNDEFINED_REFERENCE_RE.findall(log_text or ""))


def latex_log_needs_rerun(log_text: str) -> bool:
    return any(pattern in (log_text or "") for pattern in RERUN_PATTERNS)


def classify_latex_result(
    returncode: int | None,
    log_text: str,
    pdf_path: str | Path,
) -> dict:
    pdf = Path(pdf_path)
    pdf_exists = pdf.exists()
    pdf_size = pdf.stat().st_size if pdf_exists else 0
    pdf_valid = pdf_looks_valid(pdf)
    warnings = extract_latex_warnings(log_text)
    fatal_errors = extract_latex_fatal_errors(log_text)
    undefined_references = extract_undefined_references(log_text)
    needs_rerun = latex_log_needs_rerun(log_text)
    output_written = bool(OUTPUT_WRITTEN_RE.search(log_text or ""))

    if fatal_errors or not pdf_valid:
        status = "failed"
    elif returncode not in (0, None) or warnings or undefined_references or needs_rerun:
        status = "success_with_warnings"
    else:
        status = "success"

    return {
        "status": status,
        "returncode": returncode,
        "pdf_exists": pdf_exists,
        "pdf_size": pdf_size,
        "pdf_valid": pdf_valid,
        "output_written": output_written,
        "warnings": warnings,
        "fatal_errors": fatal_errors,
        "undefined_references": undefined_references,
        "needs_rerun": needs_rerun,
    }


def latex_timeout_message(
    tex_file: str | Path,
    command: Sequence[str | Path],
    timeout_seconds: int = PDF_COMPILE_TIMEOUT_SECONDS,
) -> str:
    return "\n".join(
        [
            f"LaTeX compilation timed out after {timeout_seconds} seconds.",
            f"File: {Path(tex_file)}",
            f"Command: {command_to_text(command)}",
            "Large TikZ figures may require more time.",
            "You can increase PDF_COMPILE_TIMEOUT_SECONDS.",
        ]
    )


def latex_command_not_found_message(command: Sequence[str | Path]) -> str:
    executable = str(command[0]) if command else "LaTeX"
    return (
        f"{executable} not found. Install a LaTeX distribution or update PATH.\n"
        f"Command: {command_to_text(command)}"
    )


def latex_os_error_message(
    tex_file: str | Path,
    command: Sequence[str | Path],
    error: BaseException,
) -> str:
    return "\n".join(
        [
            "LaTeX could not start because of an OS/path/permission error.",
            f"File: {Path(tex_file)}",
            f"Command: {command_to_text(command)}",
            f"Error: {error}",
        ]
    )


def latex_missing_path_message(
    tex_file: str | Path,
    command: Sequence[str | Path],
    missing_path: str | Path,
    kind: str,
) -> str:
    return "\n".join(
        [
            f"LaTeX {kind} not found.",
            f"Missing path: {Path(missing_path)}",
            f"File: {Path(tex_file)}",
            f"Command: {command_to_text(command)}",
        ]
    )


def validate_includegraphics_paths(tex_file: str | Path, cwd: str | Path) -> None:
    tex_path = Path(tex_file)
    cwd_path = Path(cwd)
    source_path = tex_path if tex_path.is_absolute() else cwd_path / tex_path
    if not source_path.exists():
        return
    content = source_path.read_text(encoding="utf-8", errors="replace")
    for match in INCLUDEGRAPHICS_RE.finditer(content):
        raw_path = match.group(1).strip()
        image_path = Path(raw_path)
        if image_path.is_absolute():
            raise FileNotFoundError(
                "Absolute image paths are not portable in MathMongo exports.\n"
                f"File: {source_path}\n"
                f"Image path: {raw_path}\n"
                "Use a relative path such as media/images/example.png."
            )
        if ".." in image_path.parts:
            raise FileNotFoundError(
                "Image paths cannot traverse outside the export directory.\n"
                f"File: {source_path}\n"
                f"Image path: {raw_path}"
            )
        candidate = cwd_path / image_path
        if candidate.exists():
            continue
        if image_path.suffix:
            raise FileNotFoundError(
                "Image referenced by \\includegraphics was not found.\n"
                f"File: {source_path}\n"
                f"Image path: {raw_path}\n"
                f"Resolved path: {candidate}"
            )


def latex_failure_message(
    tex_file: str | Path,
    command: Sequence[str | Path],
    returncode: int | None,
    log_excerpt: str = "",
    stdout: str | None = "",
    stderr: str | None = "",
) -> str:
    details = [
        "LaTeX compilation failed.",
        f"File: {Path(tex_file)}",
        f"Command: {command_to_text(command)}",
    ]
    if returncode is not None:
        details.append(f"Return code: {returncode}")
    excerpt = log_excerpt or output_tail(stdout, stderr)
    if excerpt:
        details.extend(["Relevant LaTeX log/output:", excerpt])
    return "\n".join(details)


def latex_warning_message(classification: dict) -> str:
    lines = [
        "PDF generated with warnings.",
        "The PDF file was created, but LaTeX reported warnings or unresolved references.",
    ]
    if classification.get("passes"):
        lines.append(f"LaTeX passes: {classification['passes']}")
    undefined = classification.get("undefined_references") or []
    if undefined:
        lines.append("Undefined references: " + ", ".join(undefined))
    warnings = classification.get("warnings") or []
    if warnings:
        lines.append("Warnings:")
        lines.extend(f"- {warning}" for warning in warnings[:10])
    if classification.get("needs_rerun"):
        lines.append("LaTeX requested another rerun; check labels/cross-references if this persists.")
    return "\n".join(lines)


def run_latex_command(
    command: Sequence[str | Path],
    cwd: str | Path,
    tex_file: str | Path,
    timeout_seconds: int = PDF_COMPILE_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[str]:
    command_text = [str(part) for part in command]
    if not command_text:
        raise ValueError("LaTeX command cannot be empty")
    if shutil.which(command_text[0]) is None:
        raise FileNotFoundError(latex_command_not_found_message(command_text))
    cwd_path = Path(cwd)
    if not cwd_path.exists():
        raise FileNotFoundError(
            latex_missing_path_message(tex_file, command_text, cwd_path, "working directory")
        )
    tex_path = Path(tex_file)
    tex_path_for_check = tex_path if tex_path.is_absolute() else cwd_path / tex_path
    if not tex_path_for_check.exists():
        raise FileNotFoundError(
            latex_missing_path_message(tex_file, command_text, tex_path_for_check, "source file")
        )
    validate_includegraphics_paths(tex_file, cwd_path)

    try:
        return subprocess.run(
            command_text,
            cwd=str(cwd_path),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(latex_timeout_message(tex_file, command_text, timeout_seconds)) from exc
    except (FileNotFoundError, PermissionError, OSError) as exc:
        raise type(exc)(latex_os_error_message(tex_file, command_text, exc)) from exc


def run_latex_until_stable(
    command: Sequence[str | Path],
    cwd: str | Path,
    tex_file: str | Path,
    pdf_path: str | Path,
    log_path: str | Path | None = None,
    timeout_seconds: int = PDF_COMPILE_TIMEOUT_SECONDS,
    max_passes: int = LATEX_MAX_PASSES,
) -> dict:
    max_passes = max(1, int(max_passes or 1))
    result: subprocess.CompletedProcess[str] | None = None
    classification: dict = {}
    log_file = Path(log_path) if log_path is not None else Path(tex_file).with_suffix(".log")

    for pass_number in range(1, max_passes + 1):
        result = run_latex_command(
            command,
            cwd=cwd,
            tex_file=tex_file,
            timeout_seconds=timeout_seconds,
        )
        log_text = read_text(log_file)
        if not log_text:
            log_text = "\n".join(part for part in (result.stdout or "", result.stderr or "") if part)
        classification = classify_latex_result(result.returncode, log_text, pdf_path)
        classification["passes"] = pass_number
        classification["max_passes"] = max_passes
        classification["log_text"] = log_text
        classification["log_excerpt"] = "\n".join(log_text.splitlines()[-80:])
        classification["stdout"] = result.stdout or ""
        classification["stderr"] = result.stderr or ""

        if classification["status"] == "failed":
            break
        if not classification.get("needs_rerun"):
            break

    if result is None:
        classification = classify_latex_result(None, "", pdf_path)
        classification["passes"] = 0
        classification["max_passes"] = max_passes
        classification["log_text"] = ""
        classification["log_excerpt"] = ""
        classification["stdout"] = ""
        classification["stderr"] = ""

    classification["result"] = result
    return classification
