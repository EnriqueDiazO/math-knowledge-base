# Consecuencias de los axiomas de la suma en un campo

**Tipo**: proposicion  
**Comentario**: Estas propiedades se deducen directamente de los axiomas (A1)–(A5) y garantizan unicidad de elementos y leyes de cancelación.  
**Comentario Previo**: Se basan en la existencia del neutro aditivo y de los inversos aditivos.  

**Categorías**: Álgebra, Teoría de Campos  
**Tags**: cancelación, inverso aditivo, unicidad  
**Relacionado con**: definición::campo  

**Referencia**: Rudin W., 1964, Principles of Mathematical Analysis, 1, 6, rudin1964principles  

$$
\begin{proposition}
Los axiomas de suma implican las siguientes propiedades:

\begin{itemize}
  \item[(a)] Si $x + y = x + z$, entonces $y = z$.
  \item[(b)] Si $x + y = x$, entonces $y = 0$.
  \item[(c)] Si $x + y = 0$, entonces $y = -x$.
  \item[(d)] $-(-x) = x$.
\end{itemize}

\textbf{Demostración.} Usando los axiomas (A) del campo:

Para (a): sea $x + y = x + z$. Entonces $(-x) + (x + y) = (-x) + (x + z)$, por asociatividad:
\[
((-x) + x) + y = ((-x) + x) + z \Rightarrow 0 + y = 0 + z \Rightarrow y = z.
\]

Para (b): toma $z = x$ en (a).  
Para (c): toma $z = 0$ en (a).  
Para (d): usa (c) con $x \mapsto -x$.
\end{proposition}
$$

```bibtex
@book{rudin1964principles,
  author = {Rudin, W.},
  title = {Principles of Mathematical Analysis},
  year = {1964},
  publisher = {McGraw-Hill},
  edition = {3},
  chapter = {1},
  pages = {6}
}

