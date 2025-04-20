# Desigualdad del triángulo

**Tipo**: proposicion  
**Comentario**: ¿Otra fórmula para sobrecargar a la memoria?  
**Comentario Previo**: No, si nuevamente pensamos en el triángulo...  
**Categorías**: Topología, Espacios métricos  
**Tags**: desigualdad triangular, métrica, espacio métrico  
**Relacionado con**: def_0001  
**Referencia**: Wilkiewicz, 2019, Curso de análisis y 150 problemas resueltos,1,8,Wilkiewicz2019   

$$
\textbf{Proposición 1.2.} \text{ Para todos } x, y, u \in X\\
|d(x, y) - d(x, u)| \leq d(u, y).
$$

**Demostración**:
- La desigualdad \( d(x, y) \leq d(x, u) + d(u, y) \) implica \( d(x, y) - d(x, u) \leq d(u, y) \)
- Por la misma desigualdad tenemos \( d(x, u) \leq d(x, y) + d(u, y) \), de donde \( d(x, u) - d(x, y) \leq d(u, y) \)
- Entonces \( |d(x, y) - d(x, u)| \leq d(u, y) \)

```bibtex
@book{Wilkiewicz2019,
  author = {Wilkiewicz, Antoni Wawrzyñczyk},
  title = {Curso de análisis y 150 problemas resueltos},
  year = {2019},
  publisher = {McGraw-Hill}
}

**Enlaces de salida**:   
**Enlaces de entrada**: definicion::e81fbc5f  
**Comentario personal**: Este teorema me parece esencial para introducir la noción de compacidad...  
**Inspirado en**:   
**Creado a partir de**: Discusión en clase sobre sucesiones y límites.
