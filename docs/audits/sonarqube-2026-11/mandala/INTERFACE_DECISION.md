# Interfaz elegida y transición

Decisión actual: **aplicación local independiente en TypeScript y React**, con
navegación propia, servida por el backend FastAPI existente. Es una decisión
expresa del usuario, recibida el 21 de noviembre de 2026. Sustituye la decisión
anterior de mantener Streamlit como contenedor principal. No se atribuye a una
imposibilidad técnica de CCv2: sus verificaciones siguen siendo evidencia válida
sobre edición matemática, persistencia y representación.

El detalle de implementación y aceptación está en
[FRONTEND_MIGRATION_REVIEW.md](FRONTEND_MIGRATION_REVIEW.md). Esta decisión y su
revisión no significan que la aplicación completa ya esté migrada.

## Estado comprobado al decidir

- Rama conservada: `feature/knowledge-sphere-2026-11`. Sin push ni merge.
- React, React DOM, TypeScript y Vite ya están en `frontend/advanced-reader`, con
  un único manifiesto y lockfile. Se amplía ese proyecto; no se crea otro scaffold.
- `mathmongo.advanced_reader.app.create_app` ya construye FastAPI con dependencias
  explícitas. Su launcher puede iniciar el lector sin Streamlit. Ya ofrece PDF,
  posición, numeración, anotaciones visuales, búsqueda de conceptos y evidencia;
  todavía no ofrece la aplicación de estudio completa.
- Habitación y esferas usan módulos TypeScript. `component.ts`, `room.ts` y el
  diálogo documental dependen del contrato Bridge/CCv2. Editor, fórmulas, escena,
  borradores y procedencia se reutilizan mediante adaptadores de ciclo de vida y
  transporte, conservando sus pruebas. No se reescriben sólo por usar React.
- `KnowledgeMapService.execute`, `StudyResources`, `ReadingAnnotationService`,
  Source Catalog y Source Documents conservan las operaciones canónicas. Que
  algunas utilidades estén bajo `editor/` no implica por sí solo dependencia de
  una sesión Streamlit; hay que revisar imports y efectos antes de moverlas.

## Límites de arquitectura

La aplicación compilada y su API tendrán el mismo origen local, con conexiones
MongoDB sólo en el servidor. Se mantienen las protecciones loopback, validación
de origen, límites de petición, integridad del PDF y errores sanitizados. La
separación frontend/backend es de responsabilidades y transporte; no obliga a
mantener dos servidores en la instalación de uso diario.

Se conservan MongoDB e identidades de conceptos, notas, fuentes, referencias y
documentos. Las disposiciones y exportaciones conservan sus contratos actuales.
No se añade otra persistencia semántica en el navegador. Los borradores locales
no equivalen a notas publicadas ni a conceptos.

El contexto de biblioteca será explícito y validado por el servidor. La identidad
de operación, la revisión esperada y la lectura del resultado confirmado deben
atravesar la API. Cambiar de base o de documento invalida las respuestas de
solicitudes anteriores. Cancelar una petición en el cliente no prueba que el
servidor haya cancelado una escritura.

Los componentes visuales no consultan MongoDB ni deciden reglas de persistencia.
Los routers HTTP validan y llaman servicios, sin duplicar reglas ni devolver
colecciones crudas como modelo de pantalla. FastAPI permite separar routers y
dependencias por funcionalidad ([documentación oficial](https://fastapi.tiangolo.com/tutorial/bigger-applications/)).

## Producto y convivencia

Navegación principal: Inicio, Biblioteca, Notas, Conceptos, Espacios, Cuaderno y
Ajustes. La identidad de la biblioteca es visible de forma compacta. Lectura,
contenido, borradores y acciones de estudio ocupan el espacio principal; índices,
hashes, JSON y diagnósticos internos permanecen en Ajustes → Diagnóstico.

No se incorporan funcionalidades nuevas de interfaz a `editor_streamlit.py` ni
se construye ahora una segunda navegación completa en Streamlit. Las pantallas
antiguas se conservan transitoriamente para funciones sin paridad demostrada.
Cornell/CPI no se consideran duplicados del editor de conceptos: tienen modelos,
medios y exportaciones propios.

La extracción ya iniciada se conserva y se verifica como compatibilidad, sin
ampliarla por anticipado para reconstruir todo Streamlit. Su línea base es
**5744 líneas** en el árbol de trabajo (5736 en `4204429f`). El punto de entrada
extraído tiene 29; el conjunto relacionado, contando los módulos extraídos, tiene
6134. Son **390 líneas netas añadidas**, principalmente imports, contexto y
límites de funciones; no son 5715 líneas de producto eliminadas. La gestión
histórica de mapas aún mide 1381 líneas y sigue en el inventario. El estado de
verificación de la extracción se registra por separado del último Gate aprobado.

## Criterio de primera entrega y retirada

La primera entrega es un recorrido conectado a servicios reales:

**Fuente → pasaje → nota recuperable → publicación explícita como concepto →
esfera → regreso al mismo pasaje.**

Debe funcionar en Chrome y Firefox sin proceso Streamlit, incluyendo atrás,
recarga, borrador incompleto, respuesta perdida, conflicto y cambio de biblioteca.
Un concepto visto en dos esferas conserva una sola identidad canónica.

La retirada de una página, adaptador o dependencia exige matriz de capacidades,
consumidores comprobados y regresiones de sus contratos. Se cuentan por separado
código trasladado, añadido, eliminado y generado. AppImage sigue pendiente.

SonarQube sigue siendo obligatorio por lote relevante y al cierre. Se conservan
referencia, perfiles, umbrales y exclusiones. Un Gate aprobado no cierra la
revisión manual, los archivos grandes ni la deuda heredada del repositorio.
