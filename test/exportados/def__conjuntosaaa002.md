---
id: def:conjuntosaaa002
tipo: definicion
titulo: Uniones e intersecciones arbitrarias
categorias:
- Topología
- Teoria de conjuntos
tags:
- conjunto
- notación
referencia:
  bibkey: rudin1987real
  autor: Rudin, W.
  año: 1987
  obra: Real and Complex Analysis
  edición: 3
  capitulo: 1
  pagina: 7
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
- 'def:conjuntosaaa001'
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
Denotaremos  con $ A \cup B$   y $A \cap B$ como la unión y la intersección de $A$ y $B$ respectivamente. Luego, si $\{ A_{\alpha}\}$ es una colección de conjuntos, donde $\alpha$ toma valores en algún conjunto índice $I$, escribiremos
\begin{enumerate}
\item $\bigcup_{\alpha \in I} A_{\alpha}$ para la unión de conjuntos de $\{ A_{\alpha}\}$, donde
\[ \bigcup_{\alpha \in I} A_{\alpha} := \{ x :\exists \alpha \in I: x \in A_{\alpha} \} \]
\item $\bigcap_{\alpha \in I} A_{\alpha}$ para la intersección de conjuntos de $\{ A_{\alpha}\}$.
\[ \bigcap_{\alpha \in I} A_{\alpha} := \{ x :\forall \alpha \in I: x \in A_{\alpha} \} \]
\item  Si $I$ es el conjunto de los enteros positivos, entonces
\[ \bigcup_{\alpha \in I} A_{\alpha} = \bigcup_{i=1}^{\infty} A_{\alpha} \]
\[ \bigcap_{\alpha \in I} A_{\alpha} = \bigcap_{i=1}^{\infty} A_{\alpha} \]
\end{enumerate}
\end{definition}
