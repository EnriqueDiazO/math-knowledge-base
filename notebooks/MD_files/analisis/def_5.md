# Campo ordenado

**Tipo**: definicion  
**Comentario**: Un campo ordenado es un campo que además posee una estructura de orden compatible con las operaciones algebraicas.  
**Comentario Previo**: Esta estructura permite trabajar con desigualdades dentro del campo y definir conceptos como positividad y negatividad.  

**Categorías**: Álgebra, Teoría de Campos, Estructuras Ordenadas  
**Tags**: campo ordenado, desigualdades, positividad, orden total  
**Relacionado con**: definición::campo  

**Referencia**: Rudin W., 1964, Principles of Mathematical Analysis, 1, 7, rudin1964principles  

**Enlaces de salida**: definición::positividad, definición::desigualdades  
**Enlaces de entrada**: definición::campo  
**Inspirado en**: Capítulo 1 de Rudin  
**Creado a partir de**: Formalización de estructuras algebraicas con orden  

$$
\begin{definition}
Un \textbf{campo ordenado} es un campo $F$ que además es un conjunto ordenado, y tal que:

\begin{itemize}
  \item[(i)] Si $x, y, z \in F$ y $y < z$, entonces $x + y < x + z$
  \item[(ii)] Si $x > 0$ y $y > 0$, entonces $xy > 0$
\end{itemize}

Si $x > 0$, se dice que $x$ es \textit{positivo}; si $x < 0$, se dice que $x$ es \textit{negativo}.

Por ejemplo, el conjunto $\mathbb{Q}$ de los racionales es un campo ordenado.

Las reglas conocidas para desigualdades se aplican en todo campo ordenado: multiplicar por cantidades positivas conserva desigualdades; por negativas, las invierte; ningún cuadrado es negativo, etc.
\end{definition}
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

