"""LaTeX compatibility helpers for Cornell rendering."""

from __future__ import annotations

import re
from collections.abc import Iterable
from textwrap import dedent

from editor.cornell.ui_helpers import LATEX_SNIPPET_GROUPS
from editor.cornell.ui_helpers import LatexSnippet

BEGIN_ENV_PATTERN = re.compile(r"\\begin\{([^}]+)\}")
COMMAND_PATTERN = re.compile(r"\\([A-Za-z]+|.)")

CORNELL_CUSTOM_ENVIRONMENTS = frozenset(
    {
        "definition",
        "theorem",
        "lemma",
        "proposition",
        "corollary",
        "example",
        "remark",
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
        "lstlisting",
        "dirtree",
    }
)

CORNELL_PACKAGE_ENVIRONMENTS = frozenset(
    {
        "align",
        "cases",
        "description",
        "enumerate",
        "equation",
        "itemize",
        "pmatrix",
        "proof",
    }
)


def iter_latex_snippets() -> Iterable[LatexSnippet]:
    """Yield all snippets from the shared Diario/Cornell toolbar catalog."""
    for group in LATEX_SNIPPET_GROUPS:
        yield from group.snippets


def snippet_environment_names(snippets: Iterable[LatexSnippet] | None = None) -> tuple[str, ...]:
    """Return distinct environments inserted by the shared snippet catalog."""
    source = snippets if snippets is not None else iter_latex_snippets()
    names: set[str] = set()
    for snippet in source:
        names.update(BEGIN_ENV_PATTERN.findall(snippet.snippet))
    return tuple(sorted(names))


def snippet_command_names(snippets: Iterable[LatexSnippet] | None = None) -> tuple[str, ...]:
    """Return distinct LaTeX commands inserted by the shared snippet catalog."""
    source = snippets if snippets is not None else iter_latex_snippets()
    names: set[str] = set()
    for snippet in source:
        names.update(COMMAND_PATTERN.findall(snippet.snippet))
    return tuple(sorted(names))


def supported_cornell_snippet_environments() -> tuple[str, ...]:
    """Return environments Cornell explicitly supports from snippets."""
    return tuple(sorted(CORNELL_CUSTOM_ENVIRONMENTS | CORNELL_PACKAGE_ENVIRONMENTS))


def cornell_latex_compat_preamble() -> str:
    """Return minimal LaTeX definitions needed by shared snippets in Cornell PDFs."""
    return dedent(
        r"""
        % Cornell compatibility layer for snippets shared with Diario LaTeX.
        \usepackage{xparse}
        \usepackage{amsthm}
        \usepackage[most]{tcolorbox}
        \usepackage{listings}
        \definecolor{CornellCodeBack}{rgb}{0.95,0.95,0.92}
        \definecolor{CornellCodeGray}{rgb}{0.5,0.5,0.5}
        \lstdefinestyle{cornellstyle}{
          backgroundcolor=\color{CornellCodeBack},
          basicstyle=\ttfamily\footnotesize,
          breaklines=true,
          keepspaces=true,
          showstringspaces=false,
          columns=fullflexible
        }
        \lstset{style=cornellstyle}
        \newcommand{\CornellMaybeTitle}[1]{\IfNoValueF{#1}{: #1}}
        \newcommand{\CornellBlockBox}[3]{%
          \begin{tcolorbox}[
            enhanced,
            boxrule=.45pt,
            arc=2pt,
            left=4pt,
            right=4pt,
            top=4pt,
            bottom=4pt,
            before skip=3pt,
            after skip=3pt,
            fonttitle=\bfseries,
            title={#1\CornellMaybeTitle{#2}},
            #3
          ]%
        }
        \NewDocumentEnvironment{definition}{g}{\CornellBlockBox{Definicion}{#1}{colback=blue!4,colframe=blue!55!black}}{\end{tcolorbox}}
        \NewDocumentEnvironment{theorem}{g}{\CornellBlockBox{Teorema}{#1}{colback=red!4,colframe=red!60!black}}{\end{tcolorbox}}
        \NewDocumentEnvironment{lemma}{g}{\CornellBlockBox{Lema}{#1}{colback=purple!4,colframe=purple!60!black}}{\end{tcolorbox}}
        \NewDocumentEnvironment{proposition}{g}{\CornellBlockBox{Proposicion}{#1}{colback=orange!5,colframe=orange!75!black}}{\end{tcolorbox}}
        \NewDocumentEnvironment{corollary}{g}{\CornellBlockBox{Corolario}{#1}{colback=green!5,colframe=green!55!black}}{\end{tcolorbox}}
        \NewDocumentEnvironment{example}{g}{\CornellBlockBox{Ejemplo}{#1}{colback=gray!6,colframe=gray!60}}{\end{tcolorbox}}
        \NewDocumentEnvironment{remark}{g}{\CornellBlockBox{Nota}{#1}{colback=yellow!8,colframe=yellow!65!black}}{\end{tcolorbox}}
        \newtcolorbox{context}{enhanced,boxrule=.4pt,arc=2pt,colback=gray!6,colframe=gray!60,title=Contexto,fonttitle=\bfseries}
        \newtcolorbox{reading}{enhanced,boxrule=.4pt,arc=2pt,colback=blue!5,colframe=blue!65,title=Lectura / Estudio,fonttitle=\bfseries}
        \newtcolorbox{exploration}{enhanced,boxrule=.4pt,arc=2pt,colback=purple!5,colframe=purple!65,title=Exploracion,fonttitle=\bfseries}
        \newtcolorbox{hypothesis}{enhanced,boxrule=.4pt,arc=2pt,colback=orange!6,colframe=orange!70,title=Hipotesis,fonttitle=\bfseries}
        \newtcolorbox{connections}{enhanced,boxrule=.4pt,arc=2pt,colback=teal!6,colframe=teal!65,title=Conexiones,fonttitle=\bfseries}
        \newtcolorbox{reflection}{enhanced,boxrule=.4pt,arc=2pt,colback=yellow!10,colframe=yellow!65,title=Reflexion,fonttitle=\bfseries}
        \newtcolorbox{decision}{enhanced,boxrule=.4pt,arc=2pt,colback=red!6,colframe=red!65,title=Decision,fonttitle=\bfseries}
        \newtcolorbox{openquestions}{enhanced,boxrule=.4pt,arc=2pt,colback=gray!10,colframe=black!60,title=Preguntas abiertas,fonttitle=\bfseries}
        \newtcolorbox{technical}{enhanced,boxrule=.4pt,arc=2pt,colback=CornellCodeBack,colframe=CornellCodeGray,title=Tecnica / Codigo,fonttitle=\bfseries,fontupper=\ttfamily\footnotesize}
        \newtcolorbox{nextsteps}{enhanced,boxrule=.4pt,arc=2pt,colback=green!6,colframe=green!65,title=Proximos pasos,fonttitle=\bfseries}
        \RenewDocumentEnvironment{lstlisting}{O{}}{\begin{technical}}{\end{technical}}
        \NewDocumentEnvironment{dirtree}{}{\begin{technical}}{\end{technical}}
        """
    ).strip()


def cornell_standalone_preamble(
    *,
    paper_width: str,
    paper_height: str,
    include_svg: bool = False,
    document_options: str = "12pt",
    header_comment: str | None = None,
) -> str:
    """Return the shared self-contained article preamble for Cornell PDFs."""
    comment = f"{header_comment.strip()}\n" if header_comment else ""
    svg_package = "\n\\usepackage{svg}" if include_svg else ""
    return (
        comment
        + dedent(
            rf"""
            \documentclass[{document_options}]{{article}}
            \usepackage[utf8]{{inputenc}}
            \usepackage[T1]{{fontenc}}
            \usepackage[paperwidth={paper_width},paperheight={paper_height},margin=0in]{{geometry}}
            \usepackage{{amsmath,amssymb,amsfonts}}
            \usepackage{{graphicx}}
            \usepackage{{adjustbox}}
            \usepackage[dvipsnames,svgnames]{{xcolor}}
            \usepackage{{tikz}}
            \usetikzlibrary{{calc}}
            """
        ).strip()
        + svg_package
        + "\n"
        + cornell_latex_compat_preamble()
        + "\n"
        + dedent(
            r"""
        \usepackage{hyperref}
        \pagestyle{empty}
        \setlength{\parindent}{0pt}
        \setlength{\parskip}{4pt}
        \newcommand{\CornellMainText}{\normalfont\color{black}\fontsize{10}{18.9}\selectfont}
        \newcommand{\CornellCueHeading}[1]{\begin{center}{\Huge\color{OliveGreen} #1}\end{center}}
        \newcommand{\cornellimage}[1]{\textbf{[Imagen Cornell: \detokenize{#1}]}}
        \newcommand{\CornellMainHeading}[1]{%
          \begin{minipage}{1mm}\rule{0pt}{2.1cm}\end{minipage}%
          \begin{minipage}{5.45in}{\Huge\color{RubineRed} #1}\end{minipage}\par%
        }
        \newcommand{\CornellSummaryHeading}[1]{{\color{blue}\bfseries\large #1}\par}
        """
        ).strip()
    ).strip()
