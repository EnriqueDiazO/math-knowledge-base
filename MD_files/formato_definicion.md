# Desigualdad del triángulo

**Tipo**: proposicion  
**Comentario**: Muchos problemas que el análisis estudia no son enfocados principalmente a un objeto tal como una función, una medida o un operador, sino con clases de estos objetos. La mayoría de estas clases interesantes  que ocurren en este sentido suelen ser espacios vectoriales. 

**Comentario Previo**: Un espacio vectorial es un tipo de grupo abeliano. 

**Categorías**: Espacios vectoriales, Espacios normanos, Espacios métricos  

**Tags**: vector, Espacio vectorial, grupo 

**Relacionado con**: Grupos
   
**Referencia**: Rudin, 1991, Functional Analysis, 1,5,rudin1991functional


**Demostración**:
- La desigualdad \( d(x, y) \leq d(x, u) + d(u, y) \) implica \( d(x, y) - d(x, u) \leq d(u, y) \)
- Por la misma desigualdad tenemos \( d(x, u) \leq d(x, y) + d(u, y) \), de donde \( d(x, u) - d(x, y) \leq d(u, y) \)
- Entonces \( |d(x, y) - d(x, u)| \leq d(u, y) \)

$$
Un \textit{espacio métrico} es un par $(X, d)$, donde $X$ es un conjunto y $d$ es una función real definida sobre el producto cartesiano $X \times X$ que satisface las siguientes condiciones:
\n \begin{enumerate}
\n \item $d(x, y) \geq 0$ para todos $x, y \in X$,
\n \item $d(x, y) = 0$ si y solo si $x = y$,
\n \item $d(x, y) = d(y, x)$, para todos $x, y \in X$,
\n \item para todos $x, y, u \in X$ se cumple que \n$$d(x, y) \leq d(x, u) + d(u, y).$$ 
\n \end{enumerate}
\n A la función $X$ la llamamos  la métrica del espacio $X$.
$$

```bibtex
@book{rudin1991functional,
  title={Functional Analysis},
  author={Rudin, W.},
  isbn={9780070619883},
  lccn={90005677},
  series={International series in pure and applied mathematics},
  url={https://books.google.com.mx/books?id=l7XFfDmjp5IC},
  year={1991},
  publisher={McGraw-Hill}
}
```

**Enlaces de salida**:   
**Enlaces de entrada**:   
**Comentario personal**: A partir de esta definición puedes abordar 
**Inspirado en**:
**Creado a partir de**: 
