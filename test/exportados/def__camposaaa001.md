---
id: def:camposaaa001
tipo: definicion
titulo: Campos
categorias:
- Anillos
- Grupos
tags:
- Campos
referencia:
  bibkey: rudin1964principles,
  autor: Rudin, W.
  año: 1964
  obra: Principles of Mathematical Analysis
  edición: 3
  capitulo: 1
  pagina: 5
creado_a_partir_de:
- '-'
- '-'
- '-'
- '-'
- '-'
inspirado_en:
- '-'
- --
- '-'
enlaces_entrada:
- '-'
- '-'
- '-'
- '-'
- '-'
enlaces_salida:
- '-'
- '-'
- '-'
- '-'
- '-'
---

\begin{definition}

Un \textbf{campo} es un conjunto \( F \) con dos operaciones, llamadas \textit{suma} y \textit{multiplicación}, que satisfacen los siguientes llamados “axiomas de campo” (A), (M) y (D):

\subsection*{(A) Axiomas para la suma}
\begin{itemize}
  \item[(A1)] Si \( x \in F \) y \( y \in F \), entonces su suma \( x + y \in F \).
  \item[(A2)] La suma es conmutativa: \( x + y = y + x \) para todos \( x, y \in F \).
  \item[(A3)] La suma es asociativa: \( (x + y) + z = x + (y + z) \) para todos \( x, y, z \in F \).
  \item[(A4)] \( F \) contiene un elemento \( 0 \) tal que \( 0 + x = x \) para todo \( x \in F \).
  \item[(A5)] A cada \( x \in F \) le corresponde un elemento \( -x \in F \) tal que
  \[
  x + (-x) = 0.
  \]
\end{itemize}

\subsection*{(M) Axiomas para la multiplicación}
\begin{itemize}
  \item[(M1)] Si \( x \in F \) y \( y \in F \), entonces su producto \( xy \in F \).
  \item[(M2)] La multiplicación es conmutativa: \( xy = yx \) para todos \( x, y \in F \).
  \item[(M3)] La multiplicación es asociativa: \( (xy)z = x(yz) \) para todos \( x, y, z \in F \).
  \item[(M4)] \( F \) contiene un elemento \( 1 \ne 0 \) tal que \( 1x = x \) para todo \( x \in F \).
  \item[(M5)] Si \( x \in F \) y \( x \ne 0 \), entonces existe un elemento \( 1/x \in F \) tal que
  \[
  x \cdot (1/x) = 1.
  \]
\end{itemize}

\subsection*{(D) La ley distributiva}
La ley distributiva
\[
x(y + z) = xy + xz
\]
se cumple para todos \( x, y, z \in F \).

\end{definition}
