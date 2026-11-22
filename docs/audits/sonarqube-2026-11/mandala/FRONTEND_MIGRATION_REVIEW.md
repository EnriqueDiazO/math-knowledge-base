# Revisión del encargo: aplicación independiente de estudio

La solicitud es viable aprovechando el lector React y la API FastAPI existentes.
El cambio principal es **migrar la navegación y los recorridos al cliente**, y
convertir las intenciones hoy transportadas por CCv2 en contratos HTTP. No hace
falta iniciar un segundo proyecto frontend ni sustituir MongoDB.

Esta revisión perfila el encargo; los endpoints, comandos y pantallas descritos
como propuestos no se presentan como implementados.

## Evidencia de partida

| Pieza comprobada | Estado y consecuencia |
|---|---|
| `frontend/advanced-reader/package.json`, lockfile y `vite.config.ts` | React 19.2.7, TypeScript 6.0.3 y Vite 8.1.6 declarados; reutilizar este toolchain sin actualización masiva. |
| `src/app/App.tsx` | Lector React existente, 1227 líneas: no convertirlo en contenedor de toda la aplicación. |
| `mathmongo/advanced_reader/app.py`, `routes.py`, `concept_routes.py` | FastAPI existente con servicios inyectados, PDF/rangos, posición, anotaciones y evidencia. Ampliar por routers. |
| `advanced_reader/launcher.py` | El lector puede ejecutarse sin Streamlit. Esto no acredita todavía Biblioteca, Notas ni Espacios autónomos. |
| `src/knowledge-map/component.ts`, `room.ts`, `document-dialog.ts` | Escena, habitación y edición existentes; separar el contrato Bridge del montaje CCv2. |
| `src/knowledge-map/drafts.ts` | Borradores en localStorage por scope y mapa; requiere compatibilidad de claves y traslado entre orígenes. |
| `knowledge_map/service.py`, `study_resources.py` | Intenciones validadas, registro durable de operación, revisiones y recuperación. No sustituir por escrituras CRUD genéricas. |
| `StudyResources.snapshot()` | Primeras 100 fuentes y 100 recursos por fuente; no usar ese snapshot como catálogo completo. |
| Dos borrados históricos | Edición elimina relaciones `desde`/`hasta`; exploración no las elimina y anida dos botones efímeros. Reproducción temporal confirma 0/1 relaciones restantes y una evidencia huérfana en ambas rutas; no exponer todavía un borrado equivalente en React. |
| Preparación de Lectura | Commits `1b8e8ead` y `08dd5d96`: clasificación de preparación, lectura de confirmación, borrador retenido y lectura PDF sin escritura. Reutilizar el servicio desde HTTP. |

## Precisiones que debe incorporar el encargo

1. **Una aplicación y un contrato por operación.** React compone páginas; el
   editor Tiptap/MathLive y el PDF se montan con adaptadores. No reconstruirlos
   como editores paralelos ni incrustar Streamlit. Separar navegación, cliente
   HTTP, estado de documentos, escena y componentes. Los efectos React se usan
   para sincronizar estos motores externos y limpiarlos al desmontar; las
   escrituras explícitas pertenecen a las acciones del usuario
   ([documentación oficial](https://react.dev/learn/you-might-not-need-an-effect)).
2. **Una biblioteca inequívoca por solicitud.** El backend resuelve un
   identificador opaco de perfil/biblioteca autorizado; el navegador no recibe
   URI ni elige un nombre arbitrario de base. Versionar el contexto activo y
   rechazar resultados anteriores al cambiarlo, incluso si coinciden alias o
   nombre de base en dos servidores. No mutar una conexión global compartida
   entre pestañas.
3. **Rutas durables.** Fuente, documento, nota, concepto y esfera tienen URL
   recuperable. Una recarga restaura selección y localizador; atrás no borra el
   borrador. Las búsquedas están paginadas en servidor, con resolución exacta de
   una identidad fuera del primer lote. Los nombres y autores son presentación;
   las identidades siguen siendo internas.
4. **Guardado confirmado e idempotente.** Conservar `operation_id`, revisión
   esperada y conciliación del estado persistido. Tras perder una respuesta,
   reintentar la misma operación o consultar su resultado; no generar otra nota.
   Un conflicto conserva el borrador y ofrece revisar la versión actual. Un
   timeout no significa ni éxito ni ausencia de escritura.
5. **Borradores que atraviesen la migración.** localStorage depende de origen,
   incluido el puerto. La aplicación en 8766 no puede leer directamente el
   almacenamiento del contenedor en 8501. Preparar exportación/importación
   explícita de borradores, con versión, validación, biblioteca y comprobación de
   recuperación antes de retirar el origen anterior. No anunciar copia automática
   ni vaciar el archivo antiguo al primer intento. Mantener aviso si el navegador
   no puede conservar el borrador; no confundir memoria con persistencia local.
6. **Procedencia estructurada.** Conservar `source_id`, `reference_id`,
   `document_id`, versión del PDF y ancla visual validada cuando exista, página
   PDF, etiqueta impresa y pasaje. La nota guardada y su publicación como concepto
   son dos operaciones explícitas. Volver al origen debe resolver el mismo
   documento/versión o explicar su indisponibilidad, sin redirigir a otro texto.
7. **Capacidades verificadas.** Exponer preparado, preparación compatible
   pendiente, no comprobable e incompatible. Abrir la aplicación o el diagnóstico
   sólo inspecciona. Preparar es una acción explícita y acotada, seguida de lectura
   del backend en el mismo contexto/versión. Nunca convertir una denegación de
   permisos en «faltan índices» ni una migración en preparación inocua.
8. **Mantenimiento accesible y secundario.** Cada aviso explica qué función
   afecta y una acción realizable en español. Diagnóstico conserva detalles
   técnicos. Biblioteca y Conceptos muestran contenido humano, no tarjetas
   construidas mecánicamente a partir de filas MongoDB.

## Arquitectura propuesta

```text
Frontend existente / React
  navegación y rutas
  funcionalidades: biblioteca, lectura, notas, conceptos, espacios, cuaderno
  editor documental / MathLive / PDF.js / Canvas reutilizados
  transporte HTTP tipado y almacenamiento de borradores
             │ mismo origen local
FastAPI existente
  contexto autorizado y capacidades
  routers por funcionalidad / modelos de petición y respuesta
  servicios canónicos de aplicación y repositorios existentes
             │
MongoDB canónico + contratos existentes de archivos y exportaciones
```

La instalación de uso diario puede servir el build React y la API en el mismo
proceso FastAPI. Vite queda para desarrollo. El cliente actual ya exige mismo
origen; conservar esa propiedad evita introducir CORS abierto. Si el entorno de
desarrollo usa proxy, comprobar Host y Origin reales de ese proxy con pruebas;
los puertos diferentes son orígenes distintos
([documentación oficial](https://fastapi.tiangolo.com/tutorial/cors/)).

Mantener las protecciones del servidor actual. Al ampliar escrituras, revisar
su cobertura: `_is_bounded_reader_write` hoy sólo reconoce determinadas rutas de
anotaciones/evidencia; los nuevos routers también requieren límites por operación,
validación de origen y errores sanitizados. No aplicar sin criterio el límite
64 KiB del subrayado a documentos matemáticos de hasta 100000 caracteres.

El fallback de rutas SPA debe resolver páginas válidas después de recargar,
sin transformar errores `/api` ni recursos inexistentes en respuestas HTML 200.
Verificar worker PDF, fuentes y teclado MathLive bajo los encabezados CSP reales;
las pruebas CCv2 anteriores no demuestran por sí solas esa integración.

No se prescribe una biblioteca nueva de routing o estado sin revisar primero las
necesidades. Sí se exige navegación atrás/adelante real, carga de la vista activa,
control de respuestas tardías y limpieza de listeners/controladores al salir.

## Contratos a reutilizar y ampliar

| Recorrido | Base existente | Ampliación necesaria |
|---|---|---|
| Buscar fuente y abrir PDF | Source/Reference/SourceDocument y API del lector | Catálogo bibliográfico paginado y detalle humano; conservar tres entidades distintas. |
| Seleccionar y guardar subrayado | Anotación visual S5B y ancla normalizada | Conexión con el espacio de escritura, sin copiar geometría incompatible. |
| Escribir/guardar nota | `ReadingAnnotationService`, `StudyResources.save_note` y editor compartido | HTTP con operación durable, revisión, nota devuelta y borrador conservado ante error. |
| Publicar nota como concepto | `StudyResources.publish_note`, `KnowledgeMapService.execute` | Acción explícita y procedencia; conservar identidad e idempotencia. |
| Ver concepto en esfera | StudyView/Canvas y servicio del mapa | Carga de vista y resolución exacta de recursos; sin duplicar el concepto. |
| Volver al pasaje | DocumentAccess, anclas, Page Map y navegación lógica | Ruta React resoluble, PDF/versión/página y respuesta ante origen ausente. |
| Preparar escritura | `ReadingPreparation` | GET de capacidades y POST explícito acotado; confirmar estado desde servidor. |
| Borrar concepto | Dos implementaciones divergentes | Servicio común con preflight, evidencia, referencias, medios compartidos y recuperación de fallos parciales. |
| DOI/ISBN y referencias | Captura bibliográfica canónica y proveedores ya integrados | Adaptador HTTP; mantener confirmación y detección de duplicados. |
| Exportar | Servicios LaTeX/Quarto/Cornell/CPI y guardas XDG | Peticiones explícitas, límites y entrega de artefactos; sin comandos ni rutas arbitrarias del cliente. |

No se deben replicar los métodos internos como endpoints sin revisar su contrato:
por ejemplo, el snapshot de una habitación y un catálogo de biblioteca responden
a consultas y volúmenes diferentes. Trasladar utilidades puras fuera de `editor/`
cuando ayude a sus consumidores; no copiar los servicios para conseguir otro nombre.

## Lotes y condiciones de cierre

| Lote | Resultado exigible | Verificación para avanzar |
|---|---|---|
| 0. Preservación y contrato | Decisión actualizada, inventario, baseline y extracción en curso coherente; nuevas funciones Streamlit congeladas. | Imports sin renderizado, consumidores de páginas adaptados y pruebas de alcance; no confundir reducción del entry con eliminación neta. |
| 1. Base independiente | Shell React, rutas, contexto, capacidades y biblioteca real sobre FastAPI existente. | Arranque sin Streamlit; lectura preparada y pendiente; permisos/conexión/conflicto distinguidos; recarga y atrás. |
| 2. Primer recorrido completo | Fuente → pasaje → nota → concepto → esfera → origen, con borrador recuperable. | Chrome/Firefox sobre Mongo temporal; pérdida de respuesta, reintento sin duplicado y cambio de base; pruebas de preservación LaTeX. |
| 3. Paridad de funciones | Edición/relaciones/exportación, bibliografía, organización y Cornell/CPI por sus modelos reales. | Matriz por capacidad y consumidores; contratos de borrado e imágenes compartidas; funcionalidades no sustituidas siguen accesibles. |
| 4. Retirada y cierre | Eliminar adaptadores/páginas/dependencias sin consumidores demostrados. | Arranque y recorridos sin Streamlit, matriz de paridad, cobertura, Sonar procesado y límites pendientes explícitos. |

Cada lote relevante incluye commit local, pruebas afectadas, análisis Sonar
procesado y comparación con la misma referencia. No se espera al final para
integrar el backend, ni se da por migrado un menú que abre una pantalla vacía.
El primer recorrido es un checkpoint, no el cierre de toda la migración.

## Matriz inicial de capacidades

| Capacidad | Existente | Aplicación independiente completa |
|---|---|---|
| PDF, selección, subrayados, posición y evidencia | React + HTTP con pruebas existentes | Reutilizable; falta integración con navegación global. |
| Editor visual, teclado, contenido legado y citas | Tiptap/MathLive en TS con pruebas | Adaptación de transporte y montaje pendiente. |
| Notas, publicación explícita y procedencia | Servicios canónicos + habitación CCv2 | Exposición HTTP y recorrido autónomo pendientes. |
| Esferas, disposiciones y conceptos compartidos | TS/Canvas + servicios y archivos existentes | Desacoplar Bridge y navegación pendiente. |
| Biblioteca completa y creación de fuentes | Servicios + formularios actuales | Pantallas y contratos de consulta pendientes. |
| Cuaderno, tareas, revisiones, entregables | Modelos y páginas vigentes | Migración por capacidad pendiente. |
| Cornell/CPI y exportaciones | Modelos y exportadores propios | Paridad pendiente; no autorizan retirada todavía. |
| Preparación compatible de Lectura | Servicio probado y UI en commits separados | Reutilización HTTP pendiente. |
| Diagnóstico/Conexiones/respaldos | Herramientas existentes | Ajustes React pendiente; no reconstruirlos como pantalla de inicio. |
| Borrado unificado de conceptos | Divergencia identificada en código | Reproducción completada con datos temporales; contrato común y corrección pendientes antes de conectar el borrado nuevo. |
| AppImage | Pendiente anterior | Continúa pendiente. |

## Cifras y límites del checkpoint

Último análisis terminado antes de extraer las páginas:
`14fc0f8a-09c7-41ba-8fe3-d6fd44c9ff0b`, revisión
`08dd5d9667b13b79af98c75cfbaa95614dda2982`, CE SUCCESS, Gate OK.
General **71,1 %**, nueva **82,6 %**, duplicación nueva **0,0 %**, incidencias
nuevas **0**. Frente a `be6d6c9d`: 70,9 / 82,3 %. Se conserva
PREVIOUS_VERSION `2026-11-21T16:46:16+0000`, umbrales 80/3/0 y configuración.
Este análisis no cubre la extracción posterior todavía en el árbol de trabajo.

La prueba AppTest de preparación, permisos, incompatibilidad, diagnóstico sin
escrituras y fallo de guardado/reintento pasa: **5 casos** sobre Mongo propio.
El grupo de lectura/anotaciones verificó 149 casos inicialmente y falló un helper
de prueba que no aceptaba un parámetro; corregido ese helper, pasa la regresión.
Pasan además los 43 tests de UI de anotaciones y el recorrido Chrome previo.
Estos resultados no se sustituyen por supuestos resultados del nuevo frontend.

La extracción de compatibilidad quedó en `203dd6cd`: entry de 5744 a 29 líneas,
conjunto relacionado de 6134. Se conservan veinte páginas y siete grupos de
helpers, con contexto y registro de rutas explícitos. Los contratos estáticos
ahora inspeccionan sus módulos reales. No se elimina ningún flujo de producto.

La integral ejecutó **2068 aprobadas / 9 omitidas / 1 fallida**, de 2078 casos.
La fallida era una comprobación estática que buscaba los cuatro gráficos en
Inicio; uno pertenece a Relaciones. Tras corregir sus destinos reales pasan los
cinco tests de ese módulo. Las nueve omitidas pasan en el runner Mongo propio.
Se añaden cinco pruebas de dispatch/contexto/importación y pasan. Se reconcilian
**2083 IDs Python distintos** verificados, sin sumar repeticiones como casos
nuevos; no se inventa una segunda integral monolítica posterior. El recorrido
Chrome existente pasa tras extraer las páginas. Las 209 pruebas frontend previas
siguen siendo evidencia válida porque su código no cambió. No son pruebas de la
aplicación completa independiente, todavía pendiente.

Análisis de la extracción: `0aa030c7-75e7-4ccb-91eb-f21d04ef7949`, revisión
`203dd6cd108b31e8b26e8166dbf70218d8d87ba4`, CE SUCCESS, **Gate ERROR**.
General 71,2 %, nueva 63,6 %, duplicación nueva 0,17408 %, incidencias nuevas 0.
Falla únicamente cobertura nueva frente a 80; referencia y configuración intactas.

El traslado introduce archivos cuya totalidad Sonar considera nueva. Los 32
módulos extraídos/contextuales aportan **3145 líneas medibles / 2420 sin cubrir**.
Se cotejaron por archivo las líneas y hits del XML importado con Sonar: coinciden
exactamente; **0 líneas faltantes por importación demostradas en ese conjunto**.
No se atribuye este déficit al tooling. Los tests estáticos protegen contratos,
pero no ejercitan todos los formularios y operaciones heredados.

En todo el código nuevo hay 8213 líneas, 3107 sin cubrir, más 1594 condiciones,
463 sin cubrir: 6237/9807 elementos cubiertos. Los módulos extraídos explican
2420/3570 elementos sin cubrir (67,8 %). Destacan mapas históricos (661),
relaciones (402), edición (345), creación (203) y exploración de conceptos (148).
El desglose está en NAVIGATION_COVERAGE.csv y la comprobación de importación en
NAVIGATION_REPORT_IMPORT.json. No se relaja el umbral ni se excluyen los módulos.
Cubrir las operaciones reutilizadas y los recorridos nuevos es trabajo pendiente;
no tiene sentido ocultarlo ni afirmar que el número de líneas del entry lo cierra.

Cobertura Python local: 32537/46156 = 70,49 %, con alcance diferente de Sonar.
Ruff actual: 2161 avisos; conserva deuda previa y añade avisos de estilo de la
separación (incluido bootstrap de imports y una constante ahora local). El Gate
sin incidencias automáticas no cierra esa revisión. Inventario: 363 archivos
mantenidos, 203 de pruebas, veinte mantenidos de más de mil líneas. Se cuentan
las ubicaciones nuevas y se mantienen las decisiones del resto del proyecto.
