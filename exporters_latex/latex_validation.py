from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from dataclasses import asdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from difflib import get_close_matches

from exporters_latex.unified_document import copy_latex_styles
from exporters_latex.unified_document import sanitize_source_name


PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_LATEX_DIR = PROJECT_ROOT / "templates_latex"

SAFE_FIXES = {
    r"\texbf{": r"\textbf{",
    r"\texit{": r"\textit{",
    r"\emp{": r"\emph{",
    r"\mathb{": r"\mathbb{",
    r"\mathcl{": r"\mathcal{",
    r"\mathcalle{": r"\mathcal{",
    r"\fracc{": r"\frac{",
    r"\begn{": r"\begin{",
    r"\ennd{": r"\end{",
}

CONCEPT_WRAPPER_PATTERN = re.compile(
    r"\\begin\{concept\}(?:\{([^{}]*)\})?(.*?)\\end\{concept\}",
    re.DOTALL,
)

STANDARD_COMMANDS = {
    "alpha", "beta", "gamma", "delta", "epsilon", "varepsilon", "zeta",
    "eta", "theta", "vartheta", "iota", "kappa", "lambda", "mu", "nu",
    "xi", "pi", "varpi", "rho", "varrho", "sigma", "varsigma", "tau",
    "upsilon", "phi", "varphi", "chi", "psi", "omega", "Gamma", "Delta",
    "Theta", "Lambda", "Xi", "Pi", "Sigma", "Upsilon", "Phi", "Psi",
    "Omega", "textbf", "textit", "emph", "texttt", "textsc", "section",
    "section*", "subsection", "subsubsection", "paragraph", "label", "ref",
    "eqref", "cite", "citep", "citet", "url", "href", "frac", "dfrac",
    "tfrac", "sqrt", "sum", "prod", "int", "iint", "iiint", "lim", "log",
    "ln", "sin", "cos", "tan", "max", "min", "sup", "inf", "arg", "dim",
    "ker", "operatorname", "mathbb", "mathcal", "mathfrak", "mathrm",
    "mathbf", "mathit", "mathtt", "left", "right", "big", "Big", "bigl",
    "bigr", "Bigl", "Bigr", "leq", "geq", "neq", "approx", "sim", "simeq",
    "cong", "equiv", "subset", "subseteq", "supset", "supseteq", "in",
    "notin", "emptyset", "varnothing", "cup", "cap", "setminus", "times",
    "cdot", "circ", "to", "mapsto", "rightarrow", "leftarrow",
    "Rightarrow", "Leftarrow", "Leftrightarrow", "iff", "forall", "exists",
    "nexists", "neg", "land", "lor", "wedge", "vee", "top", "bot",
    "begin", "end", "item", "itemize", "enumerate", "description", "quad",
    "qquad", "hspace", "vspace", "noindent", "small", "normalsize",
    "text", "verb", "ldots", "cdots", "vdots", "ddots", "dots", "ldotp",
    "colon", "mid", "vert", "Vert", "langle", "rangle", "ceil", "floor",
    "overline", "underline", "widehat", "widetilde", "bar", "hat", "tilde",
    "vec", "dot", "ddot", "cancel", "color", "textcolor", "begin{proof}",
}

PROJECT_COMMANDS = {
    "definicion", "teorema", "proposicion", "lema", "corolario", "ejemplo",
    "nota", "observacion", "definition", "theorem", "proposition", "lemma",
    "corollary", "example", "remark", "cthdefinicion", "cthteorema",
    "cthproposicion", "cthlema", "cthcorolario", "cthejemplo", "cthnota",
    "cthobservacion", "kbd", "dv", "pdv", "qty", "abs", "norm",
}

ALLOWED_COMMANDS = STANDARD_COMMANDS | PROJECT_COMMANDS

DEFINED_ENVIRONMENTS = {
    "document",
    "definicion",
    "teorema",
    "proposicion",
    "lema",
    "corolario",
    "ejemplo",
    "nota",
    "observacion",
    "definition",
    "theorem",
    "proposition",
    "lemma",
    "corollary",
    "example",
    "remark",
    "proof",
    "itemize",
    "enumerate",
    "description",
    "center",
    "flushleft",
    "flushright",
    "align",
    "align*",
    "equation",
    "equation*",
    "gather",
    "gather*",
    "multline",
    "multline*",
    "split",
    "matrix",
    "pmatrix",
    "bmatrix",
    "vmatrix",
    "Vmatrix",
    "cases",
    "array",
    "tabular",
    "tikzpicture",
    "lstlisting",
    "mdframed",
    "tcolorbox",
    "card",
    "notemeta",
    "context",
    "reading",
    "exploration",
    "hypothesis",
    "connections",
    "reflection",
    "decision",
    "openquestions",
    "technical",
    "nextsteps",
}


@dataclass
class LatexValidationResult:
    concept_id: str
    source: str
    title: str
    type: str
    status: str
    has_latex: bool
    unknown_commands: list[dict[str, str | None]]
    safe_fixes: list[dict[str, str]]
    balanced_braces: bool
    balanced_environments: bool
    environment_errors: list[str]
    undefined_environments: list[dict[str, str]]
    chktex_available: bool
    chktex_warnings: list[str]
    lacheck_available: bool
    lacheck_warnings: list[str]
    compile_success: bool
    log_excerpt: str
    corrected_latex_preview: str


def apply_safe_fixes(latex: str) -> tuple[str, list[dict[str, str]]]:
    corrected = latex or ""
    applied: list[dict[str, str]] = []
    if CONCEPT_WRAPPER_PATTERN.search(corrected):
        def _remove_concept_wrapper(match: re.Match) -> str:
            title = (match.group(1) or "").strip()
            body = (match.group(2) or "").strip()
            if title:
                return f"% Concept wrapper removed: {title}\n{body}"
            return f"% Concept wrapper removed\n{body}"

        corrected = CONCEPT_WRAPPER_PATTERN.sub(_remove_concept_wrapper, corrected)
        applied.append(
            {
                "from": "concept wrapper",
                "to": "removed concept wrapper",
            }
        )
    for old, new in SAFE_FIXES.items():
        if old in corrected:
            corrected = corrected.replace(old, new)
            applied.append({"from": old, "to": new})
    return corrected, applied


def find_unknown_commands(latex: str) -> list[dict[str, str | None]]:
    commands = set(re.findall(r"\\([A-Za-z@]+)\*?", latex or ""))
    unknown: list[dict[str, str | None]] = []
    allowed = sorted(ALLOWED_COMMANDS)
    for command in sorted(commands):
        if len(command) == 1:
            continue
        if command in ALLOWED_COMMANDS:
            continue
        suggestion = get_close_matches(command, allowed, n=1, cutoff=0.74)
        unknown.append(
            {
                "command": "\\" + command,
                "suggestion": ("\\" + suggestion[0]) if suggestion else None,
            }
        )
    return unknown


def braces_are_balanced(latex: str) -> bool:
    depth = 0
    escaped = False
    for char in latex or "":
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def check_environment_balance(latex: str) -> tuple[bool, list[str]]:
    pattern = re.compile(r"\\(begin|end)\{([^}]+)\}")
    stack: list[str] = []
    errors: list[str] = []
    for match in pattern.finditer(latex or ""):
        action, env = match.groups()
        if action == "begin":
            stack.append(env)
            continue
        if not stack:
            errors.append(f"Unexpected \\end{{{env}}}")
        elif stack[-1] != env:
            errors.append(f"Expected \\end{{{stack[-1]}}}, found \\end{{{env}}}")
            stack.pop()
        else:
            stack.pop()
    for env in reversed(stack):
        errors.append(f"Missing \\end{{{env}}}")
    return not errors, errors


def find_undefined_environments(latex: str) -> list[dict[str, str]]:
    envs = set(re.findall(r"\\(?:begin|end)\{([^}]+)\}", latex or ""))
    undefined = []
    for env in sorted(envs):
        if env in DEFINED_ENVIRONMENTS:
            continue
        if env == "concept":
            undefined.append(
                {
                    "environment": "concept",
                    "message": "El entorno `concept` no está definido en los templates LaTeX del proyecto.",
                    "suggestion": "Eliminar el wrapper `concept` y usar únicamente los entornos definidos en templates_latex.",
                }
            )
        else:
            suggestion = get_close_matches(env, sorted(DEFINED_ENVIRONMENTS), n=1, cutoff=0.74)
            undefined.append(
                {
                    "environment": env,
                    "message": f"Environment `{env}` is not known in the project LaTeX templates.",
                    "suggestion": suggestion[0] if suggestion else "",
                }
            )
    return undefined


def _write_validation_document(latex: str, work_dir: Path) -> Path:
    copy_latex_styles(work_dir, TEMPLATES_LATEX_DIR)
    test_path = work_dir / "fragment_test.tex"
    test_path.write_text(
        "\n".join(
            [
                r"\documentclass[12pt]{article}",
                r"\usepackage{miestilo}",
                r"\usepackage{coloredtheorem}",
                r"\begin{document}",
                "",
                latex or "",
                "",
                r"\end{document}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return test_path


def _run_tool(command: list[str], cwd: Path, timeout: int = 30) -> tuple[bool, list[str]]:
    if shutil.which(command[0]) is None:
        return False, []
    try:
        result = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except Exception as exc:
        return True, [str(exc)]
    output = "\n".join(filter(None, [result.stdout, result.stderr]))
    lines = [line for line in output.splitlines() if line.strip()]
    return True, lines


def run_chktex(tex_path: str | Path) -> tuple[bool, list[str]]:
    tex_path = Path(tex_path)
    return _run_tool(["chktex", tex_path.name], tex_path.parent)


def run_lacheck(tex_path: str | Path) -> tuple[bool, list[str]]:
    tex_path = Path(tex_path)
    return _run_tool(["lacheck", tex_path.name], tex_path.parent)


def compile_latex_fragment(latex: str, work_dir: Path | None = None) -> tuple[bool, str]:
    owned_tmp = None
    if work_dir is None:
        owned_tmp = tempfile.TemporaryDirectory(prefix="mathkb_latex_validation_")
        work_path = Path(owned_tmp.name)
    else:
        work_path = Path(work_dir)
        work_path.mkdir(parents=True, exist_ok=True)

    test_path = _write_validation_document(latex, work_path)
    log_path = work_path / "fragment_test.log"
    try:
        result = subprocess.run(
            [
                "pdflatex",
                "-interaction=nonstopmode",
                "-halt-on-error",
                test_path.name,
            ],
            cwd=str(work_path),
            capture_output=True,
            text=True,
            timeout=45,
        )
        log_excerpt = _read_tail(log_path)
        if not log_excerpt:
            log_excerpt = "\n".join(filter(None, [result.stdout, result.stderr])).splitlines()
            log_excerpt = "\n".join(log_excerpt[-60:])
        return result.returncode == 0 and (work_path / "fragment_test.pdf").exists(), log_excerpt
    except FileNotFoundError:
        return False, "pdflatex not found. Install a LaTeX distribution to validate compilation."
    except subprocess.TimeoutExpired:
        return False, "pdflatex validation timed out."
    finally:
        if owned_tmp is not None:
            owned_tmp.cleanup()


def _read_tail(path: Path, lines: int = 60) -> str:
    if not path.exists():
        return ""
    content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(content[-lines:])


def validate_latex_document(tex_path: str | Path) -> dict[str, Any]:
    tex_path = Path(tex_path)
    chktex_available, chktex_warnings = run_chktex(tex_path)
    lacheck_available, lacheck_warnings = run_lacheck(tex_path)
    try:
        result = subprocess.run(
            [
                "pdflatex",
                "-interaction=nonstopmode",
                "-halt-on-error",
                tex_path.name,
            ],
            cwd=str(tex_path.parent),
            capture_output=True,
            text=True,
            timeout=60,
        )
        pdf_path = tex_path.with_suffix(".pdf")
        compile_success = result.returncode == 0 and pdf_path.exists()
        return {
            "status": "ok" if compile_success else "error",
            "compile_success": compile_success,
            "chktex_available": chktex_available,
            "chktex_warnings": chktex_warnings,
            "lacheck_available": lacheck_available,
            "lacheck_warnings": lacheck_warnings,
            "log_excerpt": _read_tail(tex_path.with_suffix(".log")),
        }
    except FileNotFoundError:
        return {
            "status": "error",
            "compile_success": False,
            "chktex_available": chktex_available,
            "chktex_warnings": chktex_warnings,
            "lacheck_available": lacheck_available,
            "lacheck_warnings": lacheck_warnings,
            "log_excerpt": "pdflatex not found.",
        }


def validate_latex_fragment(
    latex: str,
    concept: dict[str, Any] | None = None,
    apply_fixes: bool = False,
    run_compile: bool = True,
    run_linters: bool = True,
    work_dir: Path | None = None,
) -> LatexValidationResult:
    concept = concept or {}
    original = latex or ""
    corrected, safe_fixes = apply_safe_fixes(original)
    effective_latex = corrected if apply_fixes else original

    original_unknown_commands = find_unknown_commands(original)
    effective_unknown_commands = find_unknown_commands(effective_latex)
    unknown_commands = original_unknown_commands or effective_unknown_commands
    balanced_braces = braces_are_balanced(effective_latex)
    balanced_envs, env_errors = check_environment_balance(effective_latex)
    original_undefined_envs = find_undefined_environments(original)
    effective_undefined_envs = find_undefined_environments(effective_latex)
    undefined_envs = original_undefined_envs or effective_undefined_envs

    chktex_available = shutil.which("chktex") is not None
    lacheck_available = shutil.which("lacheck") is not None
    chktex_warnings: list[str] = []
    lacheck_warnings: list[str] = []
    compile_success = True
    log_excerpt = ""

    owned_tmp = None
    validation_dir: Path | None = None
    if run_linters or run_compile:
        if work_dir is None:
            owned_tmp = tempfile.TemporaryDirectory(prefix="mathkb_latex_validation_")
            validation_dir = Path(owned_tmp.name)
        else:
            validation_dir = Path(work_dir)
            validation_dir.mkdir(parents=True, exist_ok=True)
        test_path = _write_validation_document(effective_latex, validation_dir)

        if run_linters:
            _available, chktex_warnings = _run_tool(["chktex", test_path.name], validation_dir)
            _available, lacheck_warnings = _run_tool(["lacheck", test_path.name], validation_dir)
        if run_compile:
            try:
                result = subprocess.run(
                    [
                        "pdflatex",
                        "-interaction=nonstopmode",
                        "-halt-on-error",
                        test_path.name,
                    ],
                    cwd=str(validation_dir),
                    capture_output=True,
                    text=True,
                    timeout=45,
                )
                compile_success = (
                    result.returncode == 0
                    and (validation_dir / "fragment_test.pdf").exists()
                )
                log_excerpt = _read_tail(validation_dir / "fragment_test.log")
                if not log_excerpt:
                    raw = "\n".join(filter(None, [result.stdout, result.stderr]))
                    log_excerpt = "\n".join(raw.splitlines()[-60:])
            except FileNotFoundError:
                compile_success = False
                log_excerpt = "pdflatex not found. Install a LaTeX distribution to validate compilation."
            except subprocess.TimeoutExpired:
                compile_success = False
                log_excerpt = "pdflatex validation timed out."
        if owned_tmp is not None:
            owned_tmp.cleanup()

    has_latex = bool(original.strip())
    status = "ok"
    if (
        not has_latex
        or not balanced_braces
        or not balanced_envs
        or bool(effective_undefined_envs)
        or not compile_success
    ):
        status = "error"
    elif unknown_commands or safe_fixes or chktex_warnings or lacheck_warnings:
        status = "warning"

    return LatexValidationResult(
        concept_id=str(concept.get("id") or concept.get("concept_id") or ""),
        source=str(concept.get("source") or ""),
        title=str(concept.get("titulo") or concept.get("title") or ""),
        type=str(concept.get("tipo") or concept.get("type") or ""),
        status=status,
        has_latex=has_latex,
        unknown_commands=unknown_commands,
        safe_fixes=safe_fixes,
        balanced_braces=balanced_braces,
        balanced_environments=balanced_envs,
        environment_errors=env_errors,
        undefined_environments=undefined_envs,
        chktex_available=chktex_available,
        chktex_warnings=chktex_warnings,
        lacheck_available=lacheck_available,
        lacheck_warnings=lacheck_warnings,
        compile_success=compile_success,
        log_excerpt=log_excerpt,
        corrected_latex_preview=corrected,
    )


def _db_object(db):
    return getattr(db, "db", db)


def _get_latex_doc(db, concept_id: str, source: str) -> dict[str, Any] | None:
    if hasattr(db, "get_latex_document"):
        return db.get_latex_document(concept_id, source)
    mongo_db = _db_object(db)
    return mongo_db.latex_documents.find_one({"id": concept_id, "source": source})


def validate_concept_from_mongo(
    concept_id: str,
    source: str,
    db,
    apply_fixes: bool = False,
    run_compile: bool = True,
    run_linters: bool = True,
) -> LatexValidationResult:
    if hasattr(db, "concepts"):
        concept = db.concepts.find_one({"id": concept_id, "source": source})
    else:
        concept = db.concepts.find_one({"id": concept_id, "source": source})
    concept = concept or {"id": concept_id, "source": source}
    latex_doc = _get_latex_doc(db, concept_id, source) or {}
    return validate_latex_fragment(
        latex_doc.get("contenido_latex", ""),
        concept=concept,
        apply_fixes=apply_fixes,
        run_compile=run_compile,
        run_linters=run_linters,
    )


def validate_selected_concepts_from_mongo(
    concept_keys: list[str] | list[tuple[str, str]],
    db,
    apply_fixes: bool = False,
    run_compile: bool = True,
    run_linters: bool = True,
) -> list[LatexValidationResult]:
    results = []
    for item in concept_keys:
        if isinstance(item, tuple):
            concept_id, source = item
        else:
            concept_id, source = item.split("@", 1)
        results.append(
            validate_concept_from_mongo(
                concept_id,
                source,
                db,
                apply_fixes=apply_fixes,
                run_compile=run_compile,
                run_linters=run_linters,
            )
        )
    return results


def validate_source_from_mongo(
    source: str,
    db,
    apply_fixes: bool = False,
    run_compile: bool = True,
    run_linters: bool = True,
) -> dict[str, Any]:
    if hasattr(db, "get_concepts_by_source"):
        concepts = db.get_concepts_by_source(source)
    else:
        concepts = list(db.concepts.find({"source": source}))
    results = [
        validate_concept_from_mongo(
            concept.get("id"),
            source,
            db,
            apply_fixes=apply_fixes,
            run_compile=run_compile,
            run_linters=run_linters,
        )
        for concept in concepts
    ]
    return summarize_validation_results(source, results)


def summarize_validation_results(
    source: str,
    results: list[LatexValidationResult],
) -> dict[str, Any]:
    return {
        "source": source,
        "total": len(results),
        "ok": sum(1 for r in results if r.status == "ok"),
        "warnings": sum(1 for r in results if r.status == "warning"),
        "errors": sum(1 for r in results if r.status == "error"),
        "results": [asdict(r) for r in results],
    }


def write_json_report(report: dict[str, Any], path: str | Path) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return out


def write_markdown_report(report: dict[str, Any], path: str | Path) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# LaTeX Validation Report",
        "",
        f"Source: {report.get('source', '')}",
        "",
        "## Summary",
        "",
        f"- Total concepts: {report.get('total', 0)}",
        f"- OK: {report.get('ok', 0)}",
        f"- Warnings: {report.get('warnings', 0)}",
        f"- Errors: {report.get('errors', 0)}",
        "",
    ]
    problem_results = [
        r for r in report.get("results", []) if r.get("status") != "ok"
    ]
    if problem_results:
        lines.extend(["## Problems", ""])
        for result in problem_results:
            lines.extend(
                [
                    f"### Concepto: {result.get('title') or result.get('concept_id')}",
                    "",
                    f"- ID: {result.get('concept_id')}",
                    f"- Type: {result.get('type')}",
                    f"- Status: {result.get('status')}",
                    f"- Compile success: {result.get('compile_success')}",
                ]
            )
            for item in result.get("unknown_commands", []):
                lines.append(
                    f"- Unknown command: `{item.get('command')}`"
                    + (f" -> suggestion `{item.get('suggestion')}`" if item.get("suggestion") else "")
                )
            for item in result.get("safe_fixes", []):
                lines.append(f"- Safe fix: `{item.get('from')}` -> `{item.get('to')}`")
            for error in result.get("environment_errors", []):
                lines.append(f"- Environment error: {error}")
            for item in result.get("undefined_environments", []):
                lines.append(
                    f"- Undefined environment: `{item.get('environment')}`. "
                    f"{item.get('message')} {item.get('suggestion')}"
                )
            lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def default_report_paths(source: str) -> tuple[Path, Path]:
    safe_source = sanitize_source_name(source)
    reports_dir = PROJECT_ROOT / "reports"
    return (
        reports_dir / f"{safe_source}_latex_validation.json",
        reports_dir / f"{safe_source}_latex_validation.md",
    )
