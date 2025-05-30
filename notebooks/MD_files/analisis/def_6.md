# Desigualdades fundamentales en un campo ordenado

**Tipo**: proposicion  
**Comentario**: Estas propiedades son válidas en todo campo ordenado y establecen cómo interactúan el orden y las operaciones algebraicas.  
**Comentario Previo**: Se deducen directamente de los axiomas del campo ordenado, especialmente los de la definición 1.17.  

**Categorías**: Álgebra, Campos Ordenados, Desigualdades  
**Tags**: desigualdades, campo ordenado, reciprocidad, positividad  
**Relacionado con**: definición::campo-ordenado, proposicion::propiedades-campo  

**Referencia**: Rudin W., 1964, Principles of Mathematical Analysis, 1, 8, rudin1964principles  

$$
\begin{proposition}
En todo campo ordenado se cumplen las siguientes propiedades:

\begin{itemize}
  \item[(a)] Si $x > 0$ entonces $-x < 0$, y viceversa.
  \item[(b)] Si $x > 0$ y $y < z$, entonces $xy < xz$.
  \item[(c)] Si $x < 0$ y $y < z$, entonces $xy > xz$.
  \item[(d)] Si $x \ne 0$, entonces $x^2 > 0$. En particular, $1 > 0$.
  \item[(e)] Si $0 < x < y$, entonces $0 < 1/y < 1/x$.
\end{itemize}

\textbf{Demostración.}
\begin{itemize}
  \item[(a)] Si $x > 0$, entonces $0 = -x + x > -x + 0$, así que $-x < 0$. Y viceversa.
  \item[(b)] Como $z > y$, se tiene $z - y > 0$, entonces $x(z - y) > 0$, lo que implica $xz > xy$.
  \item[(c)] Por (a), (b), y la proposición 1.16(c): $-x > 0$, $z - y > 0$ implica que $-x(z - y) > 0 \Rightarrow xz < xy$.
  \item[(d)] Si $x > 0$, entonces $x^2 > 0$ por 1.17(ii). Si $x < 0$, entonces $-x > 0$, y $(-x)^2 = x^2 > 0$.
  \item[(e)] Si $0 < x < y$, entonces $1/y < 1/x$, ya que $x^{-1} x < x^{-1} y$ y $x^{-1} > 0$.
\end{itemize}
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
  pages = {8}
}

**Enlaces de salida**: - 
**Enlaces de entrada**: definicion::3f712ac3  
**Comentario personal**: Comprender esta clasificación es clave para saber qué herramientas de análisis utilizar, especialmente en sistemas que procesan señales sostenidas como audio o telecomunicaciones.
**Inspirado en**: Sección 1.3 del libro de Willsky
**Creado a partir de**: Comparación entre energía total y potencia promedio en señales reales

