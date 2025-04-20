# Desigualdad del triángulo generalizado

**Tipo**: proposicion  
**Comentario**:   
**Comentario Previo**: 
**Categorías**: Topología, Espacios métricos  
**Tags**: desigualdad triangular, métrica, espacio métrico  
**Relacionado con**: proposicion::bf7c0b19  
**Referencia**: Wilkiewicz, 2019, Curso de análisis y 150 problemas resueltos,1,9,Wilkiewicz2019   

$$
\textbf{Proposición 1.3.} \text{ Para } x, y, u, v \in X arbitrarios\\
|d(x, y) - d(u, v)| \leq d(x, u) + d(y,v).
$$

**Demostración**:
- Dos veces aplicamos la desigualdad del triángulo para obtener  \( d(x, y) \leq d(x, u) + d(u, y) \leq d(x,u) + d(u,v) + d(y,v) \)
- Luego \(d(x,u) - d(u,v) \leq d(x,u) + d(y,v) \)
- Intercambiando los papeles de las parejas \( (x,y) \) y \( (u,v) \) y gracias a la simetría de la distancia obtenemos que  
 implica 
\( d(x, y) - d(x, u) \leq d(u, y) \)
- Por la misma desigualdad tenemos \( d(x, u) \leq d(x, y) + d(u, y) \), de donde \( d(x, u) - d(x, y) \leq d(u, y) \)
- Finalmente \( | d(x,y) - d(u,v) | \leq d(x,u) + d(y,v) \)

```bibtex
@book{Wilkiewicz2019,
  author = {Wilkiewicz, Antoni Wawrzyñczyk},
  title = {Curso de análisis y 150 problemas resueltos},
  year = {2019},
  publisher = {McGraw-Hill}
}

**Enlaces de salida**:   
**Enlaces de entrada**: proposicion::bf7c0b19  
**Comentario personal**:  
**Inspirado en**:   
**Creado a partir de**: 
