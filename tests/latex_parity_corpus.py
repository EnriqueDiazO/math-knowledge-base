"""Immutable private historical copies and explicitly authored compatibility fixtures."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

from bson import json_util

BACKUP = Path.home() / ".local/share/mathmongo/backups/mathkb_export_20260712_073927.zip"


def corpus_entries():
    """Read the authoritative ZIP, never a live user database or an extracted executable."""
    with ZipFile(BACKUP) as archive:
        entry = "mathkb_export_20260712_073927/collections/latex_documents.json"
        documents = json_util.loads(archive.read(entry))
    by_id = {row["id"]: row for row in documents}
    original = hashlib.sha256(BACKUP.read_bytes()).hexdigest()
    entries = []
    for number, identifier, label in [
        (1, "id_Curves_001", "Definición, fórmulas y referencia histórica"),
        (3, "id_Curves_017", "Demostraciones y listas anidadas"),
        (4, "id_Curves_026", "Punto no helicoidal y Punto helicoidal"),
        (5, "id_Definition_LocalMatrixSymbol_001", "Símbolo matricial local y fórmulas avanzadas"),
        (8, "IAI_antecedentes_tema", "Bibliografía y caracteres acentuados históricos"),
        (10, "def:EquivalentFormOfSlowOscillationonHalfLine", "Oscilación lenta: demostración de 325 líneas"),
    ]:
        record = by_id[identifier]
        entries.append({"case": number, "title": label, "source": record["contenido_latex"],
                        "provenance": {"kind": "historical-private-backup", "archive_sha256": original,
                                       "entry": entry, "id": identifier, "source": record["source"]},
                        "known_dependencies": ["miestilo", "notes", "mathmongo-macros"]})
    # These are newly authored test documents, not replacements claimed to be historical.
    semantic = r"""\documentclass{notes}
\newenvironment{concept}[1]{\section*{#1}}{}
\newenvironment{reference}{\begin{quote}\small}{\end{quote}}
\begin{document}
\begin{concept}{Continuidad y contexto de estudio}
\begin{context}
Estudiamos una función $f:X\to Y$ entre espacios métricos.
La escritura matemática conserva estructuras interiores y exteriores.
\end{context}
\begin{definition}{Continuidad en un punto}
La función $f$ es continua en $x_0$ si
\[
\forall\varepsilon>0\;\exists\delta>0\;\forall x\in X:
 d_X(x,x_0)<\delta\Longrightarrow d_Y(f(x),f(x_0))<\varepsilon.
\]
\end{definition}
\begin{remark}{Lectura del orden de cuantificadores}
El radio $\delta$ depende de $\varepsilon$ y del punto $x_0$.
No se intercambian los cuantificadores al editar la fórmula.
\end{remark}
\begin{proof}
Para la identidad tomamos $\delta=\varepsilon$.
\begin{enumerate}
\item Se fija una tolerancia positiva.
\item Se comprueba la implicación mediante la igualdad de distancias.
\end{enumerate}
\end{proof}
\begin{reference}
Referencia manual de prueba: apuntes propios de continuidad.
\end{reference}
\end{concept}
\end{document}
"""
    macro = r"""\documentclass{notes}
\newcommand{\normaPersonal}[1]{\left\lVert #1\right\rVert}
\newcommand{\operadorPersonal}{\mathcal{A}}
\newenvironment{argumentoPersonal}{\begin{quote}}{\end{quote}}
\begin{document}
\begin{theorem}{Cota de un operador matricial}
Sea $\operadorPersonal=\begin{pmatrix}1&2\\0&1\end{pmatrix}$.
La desigualdad triangular permite estimar $\normaPersonal{\operadorPersonal x}$.
\begin{argumentoPersonal}
\[
\normaPersonal{\operadorPersonal x}\leq
\normaPersonal{x}+\normaPersonal{(\operadorPersonal-I)x}.
\]
\end{argumentoPersonal}
\end{theorem}
\end{document}
"""
    plots = r"""\documentclass{notes}
\usepackage{tikz-cd}
\begin{document}
\section*{Dos representaciones matemáticas}
Una función, sus datos y el diagrama de composición se conservan como fuente.
\begin{tikzpicture}
\begin{axis}[width=9cm,height=5cm,xlabel={$x$},ylabel={$f(x)$},domain=-2:2,samples=41]
\addplot[blue,thick] {x^2};
\addlegendentry{$x^2$}
\addplot[red,dashed] {x+1};
\addlegendentry{$x+1$}
\end{axis}
\end{tikzpicture}
\[
\begin{tikzcd}
X \arrow[r,"f"] \arrow[dr,"g\circ f"'] & Y \arrow[d,"g"] \\
& Z
\end{tikzcd}
\]
\end{document}
"""
    complete = r"""% Documento completo nuevo: preámbulo explícito, no wrapper automático.
\documentclass[11pt]{notes}
\usepackage{mathtools}
\newcommand{\miEspacio}{\mathbb{R}^{2}}
\title{Documento completo de paridad académica}
\author{Biblioteca temporal de pruebas}
\date{24 de noviembre de 2026}
\begin{document}
\maketitle
\section{Contexto y notación}
Trabajamos en $\miEspacio$ con la norma euclídea.
\begin{definition}{Sistema de estudio}
\[
A=\begin{bmatrix}1&2\\3&4\end{bmatrix},\qquad
f(x)=\begin{cases}x^2,&x\geq0,\\-x,&x<0.\end{cases}
\]
\end{definition}
\begin{proof}
La comparación se realiza por regiones y conserva todos los casos.
\begin{itemize}
\item Para $x\geq0$, la función es polinómica.
\item Para $x<0$, la función es lineal.
\end{itemize}
\end{proof}
\section{Referencia editable}
Véase \href{https://example.org/estudio}{la página académica de prueba}.
\begin{thebibliography}{9}
\bibitem{propia} Apuntes propios. Análisis, edición y conservación de documentos.
\end{thebibliography}
\end{document}
"""
    for number, label, body in [(2, "Entornos semánticos anidados y definidos explícitamente", semantic),
                                (6, "Macros y entorno personalizado", macro),
                                (7, "PGFPlots y diagrama tikz-cd", plots),
                                (9, "Documento completo con preámbulo", complete)]:
        entries.append({"case": number, "title": label, "source": body,
                        "provenance": {"kind": "new-authored-test-document", "basis": "templates_latex/notes.cls and miestilo.sty"},
                        "known_dependencies": ["notes", "miestilo", *( ["tikz-cd"] if number == 7 else [])]})
    return sorted(entries, key=lambda item: item["case"])


def freeze_corpus(directory):
    """Create once, hash bytes and reject changes; retain private documents outside Git."""
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    manifest = []
    for item in corpus_entries():
        content = item["source"].encode("utf-8")
        path = directory / f"case-{item['case']:02}.tex"
        if path.exists():
            assert path.read_bytes() == content, "Immutable corpus changed"
        else:
            path.write_bytes(content)
            path.chmod(0o400)
        manifest.append({**{k: v for k, v in item.items() if k != "source"},
                         "path": str(path.resolve()), "sha256": hashlib.sha256(content).hexdigest(),
                         "bytes": len(content), "lines": len(item["source"].splitlines())})
    (directory / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+"\n")
    return manifest
