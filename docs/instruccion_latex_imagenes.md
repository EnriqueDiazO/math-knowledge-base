# Instruccion LaTeX para imagenes en MathMongo

Despues de subir una imagen desde Add/Edit Concept o desde Cuaderno, usa la ruta relativa registrada en `media_assets.path`.

Ejemplo:

```latex
\begin{figure}[ht]
\centering
\includegraphics[width=\textwidth]{media/images/imagen_de_prueba.png}
\caption{Descripcion opcional de la imagen}
\label{fig:imagen_de_prueba}
\end{figure}
```

Notas:

- La ruta debe ser relativa y comenzar con `media/images/`.
- No uses rutas absolutas como `/home/enriquedo/...`.
- Para PDF, el exportador copia `media/` al directorio de compilacion y carga `graphicx`.
- Si importas un ZIP y ya existe un archivo distinto con el mismo nombre, el importador remapea el archivo y actualiza las referencias importadas.
