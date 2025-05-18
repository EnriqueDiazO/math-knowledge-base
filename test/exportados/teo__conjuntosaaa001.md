---
id: teo:conjuntosaaa001
tipo: teorema
titulo: Existencia del ínfimo
categorias:
- Análisis real
- Espacios métricos
tags:
- Supremo
- Ínfimo
- Existencia
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
- 'def:conjuntosaaa010'
- 'def:conjuntosaaa011'
- 'def:conjuntosaaa012'
- '-'
enlaces_salida:
- '-'
- '-'
- '-'
- '-'
- '-'
---

\begin{theorem}
Suponga que S es un conjunto ordenado con la propiedad de la menor cota superior, $\emptyset \neq B \subset S$, y $B$ es una cota inferior. 
Sea $L$ el conjunto de todas las cotas inferiores de $B$. Entonces
\[ \alpha = sup\;\; L\]
existe en $S$, $\alpha = inf\;B \in S.$ 
\end{theorem}

\begin{proof}
Dado que $B$ está acotado inferiormente, $L$ es no vacio. Por otro lado, $L$ consiste en en exactamente aquellas $y \in S$ que satisfacen la desigualdad
\[\forall x \in B: y \leq x.\]
Por lo anterior, observamos que  todo elemento en $B$ es una cota superior de $L$. Entonces, $L$ está acotado superiormente. Como $L \subset S$, por
hipótesis $\alpha = sup \;\; L \in S$. 
\begin{enumerate}
\item Si $\gamma \leq \alpha$, entonces $\gamma$ no es una cota superior de $L$ y por lo tanto, $\gamma \notin B$. De ahi que $\forall x \in B: \alpha \leq x$.
Y por definición $\alpha \in B.$
\item Si $\alpha < \beta$, entonces $\beta \notin L$ ya que $\alpha$  es una cota superior de $L$.
\end{enumerate}
En conclusión, $\alpha$ es una cota inferior de $B$ pero todo elemento $\beta > \apha$ no es  cota inferior de $B$. Por lo tanto $\alpha = inf\;\;B$.
\end{proof}

