# Paridad funcional con v0.14.0-teaching-rc1

Referencia consultada en modo lectura: ZIP de 949 entradas con SHA256
`778c1b55dd246fc3ecb8cdfd19b7010753c0ccdad20fab38ca744fffce0b6c32`.
No se extrae sobre el repositorio ni se ejecutan sus archivos. Su entry histórico
tiene 6019 líneas; no es la línea base de 5744 de la extracción anterior. El entry
actual de compatibilidad sigue en 21 líneas, con sus páginas conservadas.

Estado de este corte: Biblioteca y núcleo Diario verificados sin Streamlit, con Gate OK;
la migración completa y el inventario de mantenibilidad siguen abiertos. **Completa** se refiere
a la operación delimitada de la fila, no a toda la familia ni a autorización para
retirar Streamlit. Se mantienen los contratos y servicios históricos.

| Capacidad / operaciones | Versión histórica y contrato | React actual / evidencia | Dependencia Streamlit restante | Estado y siguiente acción |
|---|---|---|---|---|
| Biblioteca: consultar/buscar/paginar fuentes | Catálogo S1, identidades independientes de References/Documents | Búsqueda por bibliografía, selección paginada; HTTP y Chrome/Firefox | Ninguna para esas consultas | **Completa** para lectura; conservar la administración histórica |
| Fuente: crear, consultar, editar y organizar | SourceCatalogService y CAS sobre instantánea BSON; se conservan identidades y alias | Alta, búsqueda/filtros, edición mínima recuperable, archivo/reactivación; Mongo real, HTTP y Chrome/Firefox | Eliminación física histórica no expuesta; no se retiran sus controles ni dependencias | **Completa** para creación/lectura/edición/archivo/reactivación; eliminación pendiente |
| Reference: crear, reutilizar, editar y desvincular | ReferenceCapture/SourceCatalogService; referencias compartidas y snapshots históricos | Captura, búsqueda local paginada, consentimiento para editar compartidas, desvinculación sólo sin citas de esa fuente | Decisiones bibliográficas avanzadas y retirada física no migradas | **Parcial** a nivel familia; operaciones citadas verificadas en HTTP/Mongo y ambos navegadores |
| Propuestas DOI/ISBN | Adaptadores canónicos Crossref/DataCite/Open Library; confirmación explícita | Propuesta editable disponible; pruebas de adaptadores previas válidas | Propuesta completa y correcciones recuperables/reintento verificados; edición íntegra de fichas existentes pendiente | **Parcial**: captura/recarga comprobadas; faltan todas las decisiones bibliográficas avanzadas |
| BibTeX | Parser/preview/importación selectiva canónicos, UUIDv4 estable por operación y entrada | Revisión y selección, no importa entradas no elegidas; duplicados explícitos y reintento idempotente | Resolución avanzada y fusión deliberada de duplicados siguen pendientes | **Completa** para importación selectiva y reutilización local; no equivale a fusión |
| Documento PDF/web: asociar, leer, editar y organizar | SourceDocumentService, CAS y almacenamiento validado | PDF/web, referencia, edición de metadatos, archivo/reactivación, notas y conceptos filtrados; bytes conservados | Sustitución de versión, reanclado completo y desvinculación física pendientes | **Parcial** a nivel familia; alta/consulta/edición/estados y recorrido académico completos |
| Concepto: crear/leer/editar prosa y fórmulas | ConceptoBase, identidad compuesta, contenido_latex y campos bibliográficos | Ocho tipos en creación; edición visual/fuente con CAS, duplicados y borrador; Chrome/Firefox/Mongo real | Clasificaciones avanzadas/algoritmos/otros campos todavía no editables | **Parcial**: esos campos se conservan, no se normalizan ni se eliminan |
| Concepto: eliminación | Dos rutas antiguas; ahora servicio común recuperable | Servicio y regresiones de relaciones, evidencia, medios y fallos parciales | UI React aún no conectada | **Pendiente**: confirmación contextual y reintento del mismo plan; no hacer otro borrado |
| Relaciones: crear/leer | Direccionalidad/tipo/identidades canónicas; extremos históricos compatibles | Dos conceptos, una relación en ambos detalles después de recarga | Edición/eliminación completa de relaciones | **Parcial**: crear/consultar completos, modificar/borrar pendientes |
| Esfera: explorar/abrir documento/editar | Coordenadas de presentación no cambian semántica; conceptos compartidos | Resúmenes sin carga íntegra de LaTeX, detalle a demanda y edición real | Todas las acciones avanzadas/vistas e importaciones no tienen paridad aún | **Parcial**: comprobar operaciones restantes del coordinador antes de retirar Bridge |
| Nota de lectura: crear/guardar/editar/recuperar | ReadingNote y revisión esperada; no equivale a latex_notes del Cuaderno | Desde pasaje o directamente, cita, búsqueda, borrador, pérdida de respuesta, conflicto; pruebas reales | Vínculos adicionales y herramientas completas de anotación | **Parcial** a nivel familia; escritura y recuperación delimitadas **completas** |
| Nota → concepto → esfera → origen | Incorporación explícita y enlaces de evidencia | Recorrido completo con PDF/página/pasaje; no se publica al preparar almacenamiento | Ninguna para ese recorrido | **Completa** para incorporación y retorno verificados |
| Anotaciones/subrayados | Servicios S4/S5B, versión PDF, anclajes, estados y revisión | Selección de pasaje/anotación/notas operativas, API y lector reutilizados | Revisar todos los estilos, borrados y casos de versión/reanclado | **Parcial**: no confundir un highlight del recorrido con toda la anotación |
| LaTeX: abrir y guardar fuente histórica | Texto canónico íntegro; ACE y snippets eran herramientas de autoría | Visual/fuente/protegido, acentos/enlaces seguros; cinco copias reales conservan SHA256 y metadatos | Estructuras no comprendidas se editan como fuente protegida | **Completa** para preservación probada; edición visual general **parcial** |
| LaTeX: estructuras nuevas | Entornos y argumentos reales de miestilo/notes, no HTML canónico | Bloques semánticos anidados, MathLive y LaTeX avanzado; serialización/plantillas cotejadas | No todas las construcciones tienen controles visuales | **Parcial**; el modo fuente conserva expresividad sin prometer dependencias inexistentes |
| Compilación del borrador completo | ACE/exportadores permitían inspeccionar resultado de TeX | Visual/fuente → Vista compilada del texto actual; PNG primera página y PDF completo sin guardar; Chrome/Firefox, también AppImage | Ninguna para borradores autocontenidos con paquetes instalados | **Completa** para la modalidad comprobada; recursos gráficos externos y paquetes ausentes siguen delimitados |
| Exportación TEX/PDF de texto/TikZ | Exportador individual/unificado, ZIP portable y contexto de paquetes | Selección de conceptos y notas guardadas, TEX/estilos, PDF; nuevos/mixtos/completos verificados | Recursos externos, opciones de formatos y trazabilidad editorial completa | **Parcial**: cuerpo exacto/preámbulo probados; IDs técnicos omitidos por defecto con opción explícita, también en exportadores de compatibilidad. Falta incorporar todos los recursos externos |
| TikZ: preview/ampliación/PDF | Compilación histórica, no sólo texto | Namespace aislado, PNG recortado, caché por contenido/configuración; píxeles reales comprobados tras corregir CSP | Macros/dependencias particulares requieren contexto explícito | **Completa** para figuras autocontenidas probadas; no para cualquier paquete ausente |
| Medios compartidos | Registro de medios, referencias de concepto/nota/Cornell/CPI y portabilidad | Servicios y datos conservados; el borrado común retira sólo su referencia | Subida/gestión y empaquetado de todos los recursos desde React | **Pendiente** de paridad React; no purgar bytes compartidos |
| Cuaderno y sus actividades | `latex_notes`: Diario libre, proyectos/fechas/contextos/etiquetas, referencias propias; Cornell/CPI separados | Diario React: crear/abrir/buscar/paginar/editar/guardar/recargar, asociaciones del catálogo, LaTeX exacto, CAS/reintento, TEX/PDF aislado; Mongo y Chrome/Firefox | Worklog, Backlog, Weekly, Deliverables, promociones, medios y eliminación completa siguen pendientes | **Completo el núcleo Diario delimitado**, familia Cuaderno **parcial**; ninguna retirada autorizada |
| Cornell | Modelo, regiones/cues/cuerpo/síntesis, overflow y exportación multipágina | Servicios conservados y pruebas históricas; no editor React de Cornell | Sí | **Pendiente**: adaptar experiencia sin perder regiones/medios |
| CPI | Comprensión/Producción/Integración, regiones y exportación | Servicios y colores de zonas conservados; no confundir con tipos matemáticos | Sí | **Pendiente**: editor por actividad y pruebas de desbordamiento/exportación |
| Transferencias/importación/exportación QMD/HTML | Preflight, modelos/BSON, referencias, mapas y compensación | Servicios existentes; no endpoints automáticos para cada método | Sí, varias rutas de compatibilidad/CLI | **Pendiente** de operaciones explícitas con autorización y casos privados conservados |
| Administración, migraciones y backups | Plan/dry-run/huella/backup/reconciliación; no reparación silenciosa | Preparación compatible de notas/biblioteca y diagnóstico de scope | Resto de procedimientos avanzados | **Parcial**: no convertir preparación en reparación destructiva |
| Enseñanza y auxiliares | Materiales/proyectos/Quarto, recursos y referencias | Datos y exportadores conservados | Varias herramientas aún antiguas | **Pendiente**: inventario activo, sin retirada por ausencia de coincidencias |
| AppImage | Launcher/runtime/Mongo real y XDG; no SQLite | Paquete x86_64 de 38 MiB, Python+React+19 distribuciones, cinco recorridos en Chrome/Firefox con Mongo temporal real | No inicia ni instala Streamlit. No sustituye aún todos sus flujos | **Parcial / experimental**: usa Mongo instalado, no gestiona daemon. Verificado en este host; otras distribuciones, ventana nativa y actualización pendientes |

No hay funcionalidades retiradas en estos checkpoints. Las páginas antiguas,
servicios, documentos, ZIP, referencias e identidades permanecen disponibles.
Las pruebas históricas privadas y el inventario de mantenibilidad no se cierran
porque un recorrido React funcione o porque un Gate cambie de estado.

## Checkpoint Biblioteca/Diario

- **Implementado y verificado sin Streamlit:** las operaciones delimitadas de
  Biblioteca y el núcleo Diario, con Mongo real temporal y siete recorridos por
  navegador. Pruebas: `test_library_management_http`, `test_library_concurrency`,
  `test_notebook_http`, `library-browser.mjs`, `notebook-browser.mjs` y casos de
  recuperación frontend. La escritura sigue siendo explícita, con LaTeX canónico.
- **Servicios heredados reutilizados:** catálogo/referencias/documentos, CRUD
  `latex_notes`, settings/referencias Diario, editor y exportador de bundles.
  Esto no exige una sesión Streamlit. Cornell/CPI conservan además sus servicios
  y dos caracterizaciones nuevas con persistencia real.
- **Parcial o dependiente aún de compatibilidad:** operaciones avanzadas de
  Biblioteca, borrados/medios completos, otras actividades del Cuaderno,
  Cornell/CPI, transferencias y administración, según las filas anteriores.
- **Listo para retirar:** ninguna familia completa en este corte. No se elimina
  una implementación histórica sólo porque exista una nueva página equivalente.
- **Calidad:** análisis final `b4ddd3bd-402b-4ab7-80b3-df8231fcc998`, fuente
  `a6d77fdb`, general 76,0 %, nueva 80,6 %, Gate OK. El déficit residual por
  archivo y el inventario no se cierran por ese resultado.

Especificación siguiente: [CORNELL_CPI_NEXT.md](CORNELL_CPI_NEXT.md).
