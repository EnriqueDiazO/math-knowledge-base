# Identidades adicionales en un campo

**Tipo**: proposicion  
**Comentario**: Estas identidades expresan propiedades útiles sobre el cero, el producto, y las reglas de signos en los campos.  
**Comentario Previo**: Se derivan directamente combinando los axiomas aditivos y multiplicativos.  

**Categorías**: Álgebra, Teoría de Campos  
**Tags**: signo, producto, identidad, campo  
**Relacionado con**: definición::campo  

**Referencia**: Rudin W., 1964, Principles of Mathematical Analysis, 1, 7, rudin1964principles  

$$
\begin{proposition}
Para todos $x, y \in F$, se cumple:

\begin{itemize}
  \item[(a)] $0x = 0$
  \item[(b)] Si $x \ne 0$ y $xy = 0$, entonces $y = 0$
  \item[(c)] $(-x)(-y) = xy$
  \item[(d)] $(-x)y = -(xy) = x(-y)$
\end{itemize}

\textbf{Demostración.} (a) Se sigue de $(0 + 0)x = 0x + 0x$, y por cancelación \( 0x = 0 \).  
(b) Si $xy = 0$ y $x \ne 0$, multiplicamos ambos lados por $1/x$:  
\[
(1/x)(xy) = (1/x)\cdot 0 \Rightarrow y = 0
\]

(c) y (d) se deducen usando la definición del opuesto y la conmutatividad:
\[
(-x)y = -xy, \quad x(-y) = -xy, \quad \text{por tanto } (-x)(-y) = xy
\]
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
  pages = {7}
}

