---
id: def:espaciovectorialaaa001
tipo: definicion
titulo: Espacio Vectorial
categorias:
- Espacio Vectorial
- Espacio métrico
tags:
- vector
- espacio vectorial
- espacio métrico
referencia:
  bibkey: rudin1991functional
  autor: Rudin, W.
  año: 1991
  obra: Functional Analysis
  edición: 2
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
- 'def:camposaaa001'
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
Las letras \( \mathbb{R} \) y \( \mathbb{C} \) denotarán siempre el cuerpo de los números reales y el cuerpo de los números complejos, respectivamente. Por el momento, sea \( \Phi \) igual a \( \mathbb{R} \) o \( \mathbb{C} \). Un \textit{escalar} es un elemento del cuerpo escalar \( \Phi \). 

Un \textbf{espacio vectorial sobre \( \Phi \)} es un conjunto \( X \), cuyos elementos se llaman \textit{vectores}, y en el cual están definidas dos operaciones: \textit{suma} y \textit{multiplicación por escalares}, que satisfacen las siguientes propiedades algebraicas:

\subsection*{(a)} 
Para cada par de vectores \( x \) y \( y \), existe un vector \( x + y \), tal que:
\[
x + y = y + x \quad \text{y} \quad x + (y + z) = (x + y) + z;
\]
El conjunto \( X \) contiene un vector único \( 0 \) (el \textit{vector cero} u \textit{origen} de \( X \)) tal que \( x + 0 = x \) para todo \( x \in X \); y para cada \( x \in X \), existe un vector único \( -x \) tal que \( x + (-x) = 0 \).

\subsection*{(b)} 
Para cada par \( (\alpha, x) \) con \( \alpha \in \Phi \) y \( x \in X \), existe un vector \( \alpha x \), tal que:
\[
1x = x, \quad \alpha(\beta x) = (\alpha \beta)x,
\]
y se cumplen las dos leyes distributivas:
\[
\alpha(x + y) = \alpha x + \alpha y, \quad (\alpha + \beta)x = \alpha x + \beta x.
\]

El símbolo \( 0 \) se utilizará también para el elemento cero del cuerpo escalar.

Un \textit{espacio vectorial real} es aquel para el cual \( \Phi = \mathbb{R} \); un \textit{espacio vectorial complejo} es aquel para el cual \( \Phi = \mathbb{C} \). Cualquier afirmación sobre espacios vectoriales en la que no se mencione explícitamente el cuerpo escalar, debe entenderse como aplicable a ambos casos.

\end{definition}
