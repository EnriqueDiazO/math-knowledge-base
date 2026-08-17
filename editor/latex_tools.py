"""Canonical LaTeX editing capabilities exposed by MathMongo."""

from __future__ import annotations

import re
from collections.abc import MutableMapping
from dataclasses import dataclass
from typing import Any

LATEX_SURFACE_CUADERNO = "cuaderno"
LATEX_SURFACE_CORNELL = "cornell"
LATEX_SURFACE_CPI = "cpi"
LATEX_SURFACE_CONCEPTS = "concepts"
LATEX_SURFACES = frozenset(
    {
        LATEX_SURFACE_CUADERNO,
        LATEX_SURFACE_CORNELL,
        LATEX_SURFACE_CPI,
        LATEX_SURFACE_CONCEPTS,
    }
)

CATEGORY_ORDER = (
    "Estructura",
    "Matemática",
    "Listas",
    "Tablas",
    "Código",
    "Diagramas",
    "Símbolos",
    "Bloques semánticos del cuaderno",
)

_BEGIN_ENVIRONMENT = re.compile(r"\\begin\{([^}]+)\}")
_END_ENVIRONMENT = re.compile(r"\\end\{([^}]+)\}")


@dataclass(frozen=True, slots=True)
class LatexTool:
    """One supported LaTeX fragment and its UI metadata."""

    id: str
    label: str
    category: str
    snippet: str
    help: str
    surfaces: frozenset[str] = LATEX_SURFACES
    icon: str | None = None
    packages: tuple[str, ...] = ()

    @property
    def environments(self) -> tuple[str, ...]:
        """Return environments opened by this snippet in source order."""
        return tuple(_BEGIN_ENVIRONMENT.findall(self.snippet))


@dataclass(frozen=True, slots=True)
class LatexToolGroup:
    """A non-empty visual group of tools in the canonical order."""

    title: str
    tools: tuple[LatexTool, ...]

def _tool(
    tool_id: str,
    label: str,
    category: str,
    snippet: str,
    help_text: str,
    *,
    icon: str | None = None,
    packages: tuple[str, ...] = (),
    surfaces: frozenset[str] = LATEX_SURFACES,
) -> LatexTool:
    return LatexTool(
        id=tool_id,
        label=label,
        category=category,
        snippet=snippet,
        help=help_text,
        icon=icon,
        packages=packages,
        surfaces=surfaces,
    )


_STRUCTURE_TOOLS = (
    _tool(
        "definition",
        "Definición",
        "Estructura",
        "\\begin{definition}{Título}\nContenido de la definición.\n\\end{definition}\n",
        "Inserta la caja de definición provista por el estilo de MathMongo.",
        icon=":material/description:",
        packages=("coloredtheorem",),
    ),
    _tool(
        "theorem",
        "Teorema",
        "Estructura",
        "\\begin{theorem}{Título}\nEnunciado del teorema.\n\\end{theorem}\n",
        "Inserta un teorema con el argumento de título requerido.",
        icon=":material/account_balance:",
        packages=("coloredtheorem",),
    ),
    _tool(
        "lemma",
        "Lema",
        "Estructura",
        "\\begin{lemma}{Título}\nEnunciado del lema.\n\\end{lemma}\n",
        "Inserta un lema con título.",
        icon=":material/bookmark:",
        packages=("coloredtheorem",),
    ),
    _tool(
        "proposition",
        "Proposición",
        "Estructura",
        "\\begin{proposition}{Título}\nEnunciado de la proposición.\n\\end{proposition}\n",
        "Inserta una proposición con título.",
        icon=":material/bookmark:",
        packages=("coloredtheorem",),
    ),
    _tool(
        "corollary",
        "Corolario",
        "Estructura",
        "\\begin{corollary}{Título}\nEnunciado del corolario.\n\\end{corollary}\n",
        "Inserta un corolario con título.",
        icon=":material/fork_right:",
        packages=("coloredtheorem",),
    ),
    _tool(
        "proof",
        "Prueba",
        "Estructura",
        "\\begin{proof}\nDesarrollo de la prueba.\n\\end{proof}\n",
        "Inserta el entorno de demostración de amsthm.",
        icon=":material/fact_check:",
        packages=("amsthm",),
    ),
    _tool(
        "example",
        "Ejemplo",
        "Estructura",
        "\\begin{example}{Título}\nDesarrollo del ejemplo.\n\\end{example}\n",
        "Inserta la caja de ejemplo de MathMongo.",
        icon=":material/science:",
        packages=("coloredtheorem",),
    ),
    _tool(
        "remark",
        "Nota / Remark",
        "Estructura",
        "\\begin{remark}{Título}\nContenido de la nota.\n\\end{remark}\n",
        "Inserta la caja de nota compatible con el alias remark.",
        icon=":material/sticky_note_2:",
        packages=("coloredtheorem",),
    ),
)

_MATH_TOOLS = (
    _tool(
        "equation",
        "Ecuación",
        "Matemática",
        "\\begin{equation}\n  a + b = c\n\\end{equation}\n",
        "Inserta una ecuación numerada.",
        icon=":material/functions:",
        packages=("amsmath",),
    ),
    _tool(
        "equation_star",
        "Ecuación*",
        "Matemática",
        "\\begin{equation*}\n  a + b = c\n\\end{equation*}\n",
        "Inserta una ecuación sin numeración.",
        icon=":material/functions:",
        packages=("amsmath",),
    ),
    _tool(
        "align",
        "Align",
        "Matemática",
        "\\begin{align}\n  a &= b + c \\\\\n  d &= e + f\n\\end{align}\n",
        "Alinea varias ecuaciones y conserva numeración.",
        icon=":material/format_align_left:",
        packages=("amsmath",),
    ),
    _tool(
        "align_star",
        "Align*",
        "Matemática",
        "\\begin{align*}\n  a &= b + c \\\\\n  d &= e + f\n\\end{align*}\n",
        "Alinea varias ecuaciones sin numeración.",
        icon=":material/format_align_left:",
        packages=("amsmath",),
    ),
    _tool(
        "gather",
        "Gather",
        "Matemática",
        "\\begin{gather}\n  a + b = c \\\\\n  d + e = f\n\\end{gather}\n",
        "Agrupa ecuaciones centradas en líneas independientes.",
        icon=":material/format_align_center:",
        packages=("amsmath",),
    ),
    _tool(
        "cases",
        "Cases",
        "Matemática",
        "\\[\nf(x) = \\begin{cases}\n  x^2, & x \\ge 0, \\\\\n  -x, & x < 0.\n\\end{cases}\n\\]\n",
        "Inserta una función definida por casos dentro de modo matemático.",
        icon=":material/call_split:",
        packages=("amsmath",),
    ),
    _tool(
        "pmatrix",
        "PMatrix",
        "Matemática",
        "\\[\n\\begin{pmatrix}\n  a & b \\\\\n  c & d\n\\end{pmatrix}\n\\]\n",
        "Inserta una matriz delimitada por paréntesis.",
        icon=":material/grid_on:",
        packages=("amsmath",),
    ),
    _tool(
        "bmatrix",
        "BMatrix",
        "Matemática",
        "\\[\n\\begin{bmatrix}\n  a & b \\\\\n  c & d\n\\end{bmatrix}\n\\]\n",
        "Inserta una matriz delimitada por corchetes.",
        icon=":material/grid_on:",
        packages=("amsmath",),
    ),
    _tool(
        "determinant",
        "Determinante",
        "Matemática",
        "\\[\n\\begin{vmatrix}\n  a & b \\\\\n  c & d\n\\end{vmatrix}\n\\]\n",
        "Inserta un determinante con barras verticales.",
        icon=":material/calculate:",
        packages=("amsmath",),
    ),
)

_LIST_TOOLS = (
    _tool(
        "itemize",
        "Itemize",
        "Listas",
        "\\begin{itemize}\n  \\item Primer elemento.\n  \\item Segundo elemento.\n\\end{itemize}\n",
        "Inserta una lista con viñetas y dos elementos editables.",
        icon=":material/format_list_bulleted:",
    ),
    _tool(
        "enumerate",
        "Enumerate",
        "Listas",
        "\\begin{enumerate}\n  \\item Primer paso.\n  \\item Segundo paso.\n\\end{enumerate}\n",
        "Inserta una lista numerada y dos elementos editables.",
        icon=":material/format_list_numbered:",
    ),
    _tool(
        "description",
        "Description",
        "Listas",
        "\\begin{description}\n  \\item[Término] Descripción.\n\\end{description}\n",
        "Inserta una lista de términos y descripciones.",
        icon=":material/format_list_bulleted:",
    ),
)

_TABLE_TOOLS = (
    _tool(
        "tabular",
        "Tabla básica",
        "Tablas",
        "\\begin{tabular}{ll}\n  A & B \\\\\n  1 & 2\n\\end{tabular}\n",
        "Inserta una tabla sencilla de dos columnas sin flotante.",
        icon=":material/table:",
        packages=("array",),
    ),
    _tool(
        "booktabs",
        "Booktabs",
        "Tablas",
        "\\begin{tabular}{@{}ll@{}}\n  \\toprule\n  Columna A & Columna B \\\\\n  \\midrule\n  Dato 1 & Dato 2 \\\\\n  \\bottomrule\n\\end{tabular}\n",
        "Inserta una tabla con reglas tipográficas de booktabs.",
        icon=":material/table_rows:",
        packages=("booktabs",),
    ),
    _tool(
        "tabularx",
        "TabularX",
        "Tablas",
        "\\begin{tabularx}{\\linewidth}{lX}\n  \\toprule\n  Clave & Descripción \\\\\n  \\midrule\n  A & Texto que se ajusta al ancho disponible. \\\\\n  \\bottomrule\n\\end{tabularx}\n",
        "Inserta una tabla cuya columna X se adapta al ancho disponible.",
        icon=":material/view_column:",
        packages=("tabularx", "booktabs"),
    ),
)

_CODE_TOOLS = (
    _tool(
        "listing",
        "Código",
        "Código",
        "\\begin{lstlisting}\ncodigo_de_ejemplo()\n\\end{lstlisting}\n",
        "Inserta un listing genérico sin declarar un lenguaje ficticio.",
        icon=":material/code:",
        packages=("listings",),
    ),
    _tool(
        "listing_python",
        "Código Python",
        "Código",
        "\\begin{lstlisting}[language=Python]\ndef ejemplo(valor):\n    return valor * 2\n\\end{lstlisting}\n",
        "Inserta un listing con el lenguaje Python incluido por listings.",
        icon=":material/code:",
        packages=("listings",),
    ),
    _tool(
        "algorithm",
        "Algoritmo",
        "Código",
        "\\begin{algoritmo}[language=Python]{Título del algoritmo}\ndef resolver(dato):\n    return dato\n\\end{algoritmo}\n",
        "Inserta la caja de algoritmo definida por miestilo.sty.",
        icon=":material/account_tree:",
        packages=("tcolorbox", "listings"),
    ),
)

_DIAGRAM_TOOLS = (
    _tool(
        "tikzpicture",
        "TikZ básico",
        "Diagramas",
        "\\begin{tikzpicture}\n  \\draw (0,0) -- (2,0);\n\\end{tikzpicture}\n",
        "Inserta un lienzo TikZ mínimo.",
        icon=":material/draw:",
        packages=("tikz",),
    ),
    _tool(
        "tree",
        "Árbol",
        "Diagramas",
        "\\begin{tikzpicture}\n  \\Tree [.{Raíz} {Hijo 1} {Hijo 2} ]\n\\end{tikzpicture}\n",
        "Inserta un árbol pequeño con tikz-qtree.",
        icon=":material/account_tree:",
        packages=("tikz-qtree",),
    ),
    _tool(
        "dirtree",
        "DirTree",
        "Diagramas",
        "\\dirtree{%\n  .1 proyecto.\n  .2 carpeta.\n  .3 archivo.tex.\n}\n",
        "Inserta una estructura de directorios con el comando de dirtree.",
        icon=":material/folder:",
        packages=("dirtree",),
    ),
    _tool(
        "pgfplots",
        "PGFPlots",
        "Diagramas",
        "\\begin{tikzpicture}\n  \\begin{axis}[xlabel={$x$},ylabel={$f(x)$}]\n    \\addplot[domain=-2:2,samples=50] {x^2};\n  \\end{axis}\n\\end{tikzpicture}\n",
        "Inserta una gráfica cartesiana mínima con pgfplots.",
        icon=":material/show_chart:",
        packages=("pgfplots",),
    ),
)


def _symbol(
    tool_id: str,
    label: str,
    command: str,
    help_text: str,
) -> LatexTool:
    return _tool(
        tool_id,
        label,
        "Símbolos",
        rf"\({command}\)",
        help_text,
        packages=("amsmath", "amssymb"),
    )


_SYMBOL_TOOLS = (
    _symbol("sum", "Σ", r"\sum_{i=1}^{n}", "Inserta una suma finita frecuente."),
    _symbol("product", "Π", r"\prod_{i=1}^{n}", "Inserta un producto finito."),
    _symbol("integral", "∫", r"\int_{a}^{b}", "Inserta una integral definida."),
    _symbol("partial", "∂", r"\partial", "Inserta el símbolo de derivada parcial."),
    _symbol("infinity", "∞", r"\infty", "Inserta infinito."),
    _symbol("right_arrow", "→", r"\rightarrow", "Inserta una flecha hacia la derecha."),
    _symbol("in", "∈", r"\in", "Inserta pertenencia a un conjunto."),
    _symbol("not_in", "∉", r"\notin", "Inserta no pertenencia a un conjunto."),
    _symbol("subseteq", "⊆", r"\subseteq", "Inserta inclusión de conjuntos."),
    _symbol("union", "∪", r"\cup", "Inserta unión de conjuntos."),
    _symbol("intersection", "∩", r"\cap", "Inserta intersección de conjuntos."),
    _symbol("emptyset", "∅", r"\emptyset", "Inserta el conjunto vacío."),
    _symbol("real_numbers", "ℝ", r"\mathbb{R}", "Inserta el conjunto de los reales."),
    _symbol("forall", "∀", r"\forall", "Inserta el cuantificador universal."),
    _symbol("exists", "∃", r"\exists", "Inserta el cuantificador existencial."),
    _symbol("implies", "⇒", r"\implies", "Inserta implicación lógica."),
    _symbol("iff", "⇔", r"\iff", "Inserta equivalencia lógica."),
    _symbol("alpha", "α", r"\alpha", "Inserta alfa minúscula."),
    _symbol("beta", "β", r"\beta", "Inserta beta minúscula."),
    _symbol("gamma", "γ", r"\gamma", "Inserta gamma minúscula."),
    _symbol("delta", "δ", r"\delta", "Inserta delta minúscula."),
    _symbol("varepsilon", "ε", r"\varepsilon", "Inserta épsilon variante."),
    _symbol("theta", "θ", r"\theta", "Inserta theta minúscula."),
    _symbol("lambda", "λ", r"\lambda", "Inserta lambda minúscula."),
    _symbol("mu", "μ", r"\mu", "Inserta mu minúscula."),
    _symbol("pi", "π", r"\pi", "Inserta pi minúscula."),
    _symbol("sigma", "σ", r"\sigma", "Inserta sigma minúscula."),
    _symbol("phi", "φ", r"\phi", "Inserta phi minúscula."),
    _symbol("omega", "ω", r"\omega", "Inserta omega minúscula."),
    _tool(
        "osc_operator",
        "osc",
        "Símbolos",
        r"\(\osc(f)\)",
        "Inserta el operador de oscilación compartido por los exportadores.",
        packages=("mathmongo-macros",),
    ),
    _tool(
        "max_operator",
        "Max",
        "Símbolos",
        r"\(\Max(A)\)",
        "Inserta el operador Max definido por MathMongo.",
        packages=("mathmongo-macros",),
    ),
)

_CUADERNO_ONLY = frozenset({LATEX_SURFACE_CUADERNO})
_SEMANTIC_TOOLS = tuple(
    _tool(
        tool_id,
        label,
        "Bloques semánticos del cuaderno",
        f"\\begin{{{environment}}}\nContenido.\n\\end{{{environment}}}\n",
        help_text,
        icon=icon,
        packages=("notes",),
        surfaces=_CUADERNO_ONLY,
    )
    for tool_id, label, environment, help_text, icon in (
        ("context", "Contexto", "context", "Registra la situación de trabajo.", ":material/location_on:"),
        ("reading", "Lectura", "reading", "Registra estudio o lectura.", ":material/menu_book:"),
        ("exploration", "Exploración", "exploration", "Desarrolla una exploración inicial.", ":material/explore:"),
        ("hypothesis", "Hipótesis", "hypothesis", "Formula una hipótesis de trabajo.", ":material/lightbulb:"),
        ("connections", "Conexiones", "connections", "Relaciona ideas o conceptos.", ":material/hub:"),
        ("reflection", "Reflexión", "reflection", "Registra una reflexión metacognitiva.", ":material/psychology:"),
        ("decision", "Decisión", "decision", "Documenta una decisión tomada.", ":material/check_circle:"),
        ("openquestions", "Preguntas abiertas", "openquestions", "Conserva preguntas aún no resueltas.", ":material/help:"),
        ("technical", "Técnica", "technical", "Registra detalle técnico o código breve.", ":material/build:"),
        ("nextsteps", "Próximos pasos", "nextsteps", "Enumera acciones siguientes.", ":material/next_plan:"),
        ("checkpoint", "Punto de control", "checkpoint", "Marca una comprobación intermedia.", ":material/flag:"),
        ("warningnote", "Advertencia", "warningnote", "Destaca una advertencia.", ":material/warning:"),
        ("successnote", "Resultado esperado", "successnote", "Destaca el resultado esperado.", ":material/task_alt:"),
        ("errornote", "Error", "errornote", "Explica un resultado inesperado.", ":material/error:"),
    )
)

LATEX_TOOLS = (
    *_STRUCTURE_TOOLS,
    *_MATH_TOOLS,
    *_LIST_TOOLS,
    *_TABLE_TOOLS,
    *_CODE_TOOLS,
    *_DIAGRAM_TOOLS,
    *_SYMBOL_TOOLS,
    *_SEMANTIC_TOOLS,
)


def latex_tools_for_surface(surface: str) -> tuple[LatexTool, ...]:
    """Return the tools explicitly supported by one editing surface."""
    if surface not in LATEX_SURFACES:
        raise ValueError(f"Unknown LaTeX editing surface: {surface}")
    return tuple(tool for tool in LATEX_TOOLS if surface in tool.surfaces)


def latex_tool_by_id(tool_id: str) -> LatexTool:
    """Resolve one tool by its stable technical ID."""
    for tool in LATEX_TOOLS:
        if tool.id == tool_id:
            return tool
    raise KeyError(tool_id)


def latex_tool_groups(surface: str) -> tuple[LatexToolGroup, ...]:
    """Group a surface's tools without maintaining parallel snippet lists."""
    tools = latex_tools_for_surface(surface)
    return tuple(
        LatexToolGroup(category, tuple(tool for tool in tools if tool.category == category))
        for category in CATEGORY_ORDER
        if any(tool.category == category for tool in tools)
    )


def append_latex_snippet(existing: str, snippet: str) -> str:
    """Append a snippet without erasing existing LaTeX content."""
    current = existing or ""
    insert = snippet or ""
    if not insert:
        return current
    if current and not current.endswith("\n"):
        current += "\n"
    return current + insert + ("\n" if not insert.endswith("\n") else "")


def queue_latex_snippet(
    state: MutableMapping[str, Any],
    *,
    snippet_key: str,
    trigger_key: str,
    snippet: str,
) -> None:
    """Queue one insertion using only transient Streamlit session keys."""
    state[snippet_key] = snippet
    state[trigger_key] = bool(snippet)


def apply_queued_latex_snippet(
    state: MutableMapping[str, Any],
    *,
    text_key: str,
    snippet_key: str,
    trigger_key: str,
) -> bool:
    """Append one queued fragment atomically and clear its transient flags."""
    if not state.get(trigger_key) or not state.get(snippet_key):
        return False
    state[text_key] = append_latex_snippet(
        str(state.get(text_key, "") or ""),
        str(state[snippet_key]),
    )
    state[trigger_key] = False
    state[snippet_key] = ""
    return True


def environment_pairs(snippet: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return opened and closed environments for registry contract checks."""
    return (
        tuple(_BEGIN_ENVIRONMENT.findall(snippet)),
        tuple(_END_ENVIRONMENT.findall(snippet)),
    )


__all__ = [
    "CATEGORY_ORDER",
    "LATEX_SURFACE_CONCEPTS",
    "LATEX_SURFACE_CORNELL",
    "LATEX_SURFACE_CPI",
    "LATEX_SURFACE_CUADERNO",
    "LATEX_SURFACES",
    "LATEX_TOOLS",
    "LatexTool",
    "LatexToolGroup",
    "append_latex_snippet",
    "apply_queued_latex_snippet",
    "environment_pairs",
    "latex_tool_by_id",
    "latex_tool_groups",
    "latex_tools_for_surface",
    "queue_latex_snippet",
]
