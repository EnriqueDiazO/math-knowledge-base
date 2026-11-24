# Checkpoint Biblioteca y Diario — 24 de noviembre de 2026

Rama conservada: `feature/knowledge-sphere-2026-11`. Recuperación en `442aa5a4`;
análisis final de código `a6d77fdb7fb056e8f225fdc983254926c6b8b9c0`.
No se hizo push, merge, reset ni limpieza destructiva del árbol.

## Abrir la aplicación actual sin Streamlit

Desde la raíz del repositorio, con MongoDB local disponible:

```bash
.venv/bin/python -m mathmongo.advanced_reader \
  --host 127.0.0.1 --port 8766 --database nombre_de_tu_biblioteca
```

Abrir `http://127.0.0.1:8766/study`. Elegir explícitamente la base evita confundir
bibliotecas. Abrirla no prepara índices ni publica borradores. Los ensayos de este
checkpoint usaron procesos y bases temporales propios, nunca MathV0.

## Capacidades verificadas

- Biblioteca: crear/recuperar/editar fuentes, buscar y filtrar, DOI/ISBN y captura
  manual existentes, reutilizar referencias locales, importar BibTeX selectivo,
  editar referencias compartidas con consentimiento, adjuntar/editar/archivar y
  reactivar documentos, leer, escribir notas y consultar conceptos relacionados.
- Diario de Cuaderno: crear/abrir/buscar/paginar, editar con Tiptap/MathLive,
  conservar LaTeX avanzado/TikZ, recuperar tras recargar, referencias propias del
  catálogo, conflictos/reintentos, y exportar TEX/PDF por el sandbox existente.
- Compatibilidad: dos fallos corregidos fuera de React, en confirmaciones de
  relaciones filtradas y alcance de exportación masiva. No se retiraron flujos.

## Verificación y calidad

2181 casos Python distintos aprobados: 2161 de integral, sus 9 opt-ins ejecutados
a continuación, y 11 nuevas caracterizaciones sin solapamiento. Ningún caso
queda omitido sin ejecutar; los 50 históricos privados están en la integral.
297 frontend; ESLint, TypeScript y builds correctos. Siete recorridos por navegador:
Chrome 158.0.8127.36 y Firefox 151.0. Persistencia real, pérdida de respuesta,
concurrencia, macros, TikZ y cinco documentos históricos exactos comprobados.

| Resultado Sonar procesado | General | Nueva | Gate |
|---|---:|---:|---|
| Anterior `f00aa5ac` | 74,2 % | 74,5 % | ERROR |
| Biblioteca `720f8fbf` | 73,9 % | 73,6 % | ERROR |
| Diario `03ee4a3a` | 74,1 % | 74,1 % | ERROR |
| Final `a6d77fdb` | **76,0 %** | **80,6 %** | **OK** |

Análisis final `b4ddd3bd-402b-4ab7-80b3-df8231fcc998`, CE SUCCESS.
Nueva duplicación 0,10067 %; incidencias nuevas 0. Referencia, perfiles,
reglas, exclusiones y umbrales conservados. Las cifras locales de LCOV son otro
alcance: 81,92 % de líneas y 69,33 % de ramas del frontend tras unidades/navegador.

[Resultado completo](LIBRARY_NOTEBOOK_FINAL_RESULTS.json),
[desglose por archivo](LIBRARY_NOTEBOOK_FINAL_COVERAGE.csv),
[secuencia reproducible de análisis](REPEAT_REACT_ANALYSIS.md) y
[registro acumulativo](FULL_MIGRATION_WORKLOG.md).

## Evidencias locales de operaciones reales

- [Biblioteca: edición y recuperación tras perder la respuesta](../../../../evidence/sonar/independent-study/chrome/library-source-edited-after-lost-reply.png).
- [Biblioteca: referencia compartida](../../../../evidence/sonar/independent-study/firefox/library-shared-reference-edit.png).
- [Diario: creación visual con fórmula y TikZ protegido](../../../../evidence/sonar/independent-study/chrome/notebook-visual-math-and-protected-tikz.png).
- [Diario guardado y recuperado](../../../../evidence/sonar/independent-study/chrome/notebook-saved-and-recovered.png).
- [Diario: filtro por fuente en Firefox](../../../../evidence/sonar/independent-study/firefox/notebook-source-linked-entries.png).
- [PDF compilado real del Diario](../../../../evidence/sonar/independent-study/chrome/notebook-visual.pdf).

Las evidencias y los PDFs de prueba permanecen locales en la ruta ignorada
`evidence/sonar`; no se versionan bases temporales, documentos privados,
credenciales ni paquetes generados innecesarios.

## Tamaños y separación de responsabilidades

No se presenta el nuevo Diario como una reducción de líneas: añade capacidades.
El punto de entrada mantiene sus 21 líneas; las páginas históricas no crecen con
funcionalidades nuevas. Se cuenta cada módulo de actividad/documento/estado.

| Archivo | Líneas al recuperar `442aa5a4` | Líneas al cerrar | Responsabilidad |
|---|---:|---:|---|
| editor/editor_streamlit.py | 21 | 21 | Integración mínima de compatibilidad |
| editor/cuaderno_page.py | 4122 | 4122 | Actividades históricas conservadas |
| mathdatabase/mathmongo.py | 577 | 591 | CRUD canónico y enlace explícito a base ya elegida |
| editor/diary_note_persistence.py | 36 | 38 | Persistencia mínima y CAS opcional |
| editor/pdf_export.py | 1052 | 1058 | Exportación canónica, UI cargada bajo demanda |
| mathmongo/study/notebook.py | — (nuevo) | 190 | Operaciones Diario y reconstrucción documental |
| mathmongo/study/notebook_routes.py | — (nuevo) | 145 | Adaptación HTTP y validaciones de frontera |
| frontend/advanced-reader/src/study/notebook-state.ts | — (nuevo) | 133 | Borrador, cambios mínimos y rebase explícito |
| frontend/advanced-reader/src/study/NotebookReferences.tsx | — (nuevo) | 78 | Selección bibliográfica contextual |
| frontend/advanced-reader/src/study/NotebookWorkspace.tsx | — (nuevo) | 327 | Composición del editor y flujo de guardado |
| frontend/advanced-reader/src/study/NotebookPages.tsx | — (nuevo) | 186 | Navegación, búsqueda y apertura a demanda |
| frontend/advanced-reader/src/study/ExportActions.tsx | 67 | 101 | Descarga común para conceptos/notas/Diario |

Las 37 líneas mantenidas reemplazadas no son 37 líneas de funciones obsoletas:
corresponden a integración, firmas y placeholder sustituido. No se eliminó una
función por ausencia de coincidencias. Doce líneas del runner cambiaron de lugar
para aislar las cohortes. Los assets regenerados son otra categoría.
[Inventario y decisiones de los veinte mayores](LARGE_FILES.md).

## Pendientes y siguiente corte

Biblioteca sigue parcial para borrado físico, planes/fusión avanzada de referencias
y sustitución/reanclado de versiones. Cuaderno mantiene pendientes de medios,
borrado, preferencias editoriales, Worklog/Backlog/Weekly/Deliverables y promociones.
Cornell/CPI conservan modelos y servicios: [especificación siguiente](CORNELL_CPI_NEXT.md)
y dos caracterizaciones con Mongo real. Ninguna familia está lista para retirar
su implementación completa de Streamlit. Transferencias, administración y
mantenibilidad continúan en el inventario aunque el Gate sea OK.

La AppImage anterior permanece intacta y experimental; no contiene los cambios
nuevos. El backend actual se importa con sus mismas 19 distribuciones en Python
sin site-packages externos ni Streamlit. No se reconstruyó ni se cambiaron los
requisitos externos de MongoDB/LaTeX. El siguiente lote recomendado es Cornell:
CAS estructurado, edición por región, ajuste/overflow y exportación aislada.
