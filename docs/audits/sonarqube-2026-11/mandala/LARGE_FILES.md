# Revisión de archivos grandes

Medida de tamaño: **líneas físicas**, incluidos comentarios y espacios. No es
`ncloc` de Sonar. El CSV reproducible se obtiene con
`python -m scripts.repository_inventory`; distingue fuente mantenida, pruebas,
configuración, recursos, dependencias y salida generada. El encabezado histórico
«Auto-generated» de cuaderno_page.py no lo convierte en salida regenerable: el
script de extracción mencionado ya no existe y hoy se mantiene directamente.

Esta inspección combina la evidencia anterior aún aplicable con lectura de las
responsabilidades, funciones largas y fronteras de escritura actuales. No se
marca un archivo como inspeccionado únicamente por contarlo con AST/Sonar.
Los estados y tamaños finales se actualizarán después de las extracciones y
regresiones; los siguientes son los veinte mayores al abrir esta continuación.

| Archivo | Líneas al revisar | Responsabilidades y evidencia examinada | Decisión / estado |
|---|---:|---|---|
| editor/editor_streamlit.py | 5714 | Navegación, conexión, dashboard, captura/edición y mapas; ramas reales y callbacks, scope de base, guardado y exportación | **Corrección/refactorización pendiente**: UTC corregido; composición de páginas todavía monolítica. Sustituir sólo rutas con paridad comprobada; conserva por ahora campos bibliográficos, medios y herramientas que el editor contextual aún no cubre. |
| editor/cuaderno_page.py | 4122 | Diario, promoción, Worklog, Backlog, Weekly, Deliverables; render_cuaderno de 1874 líneas, queries y fechas | **Corrección/refactorización pendiente**: reloj UTC corregido sin migración. Las seis pestañas y sus estados justifican separar composición por flujo; no eliminar el cuaderno ni sus entidades para reducir tamaño. |
| visualizations/grafoconocimiento.py | 3670 | Grafo PyVis, normalización, SVG, snapshots y HTML autocontenido; exportar_html incorpora unas 2605 líneas de JS/CSS/HTML | **Corrección/refactorización pendiente**: reloj corregido; separar plantilla/control del adaptador Python y caracterizar salida y navegación. No es un renderizador muerto: consumidores en exportación CLI, mapas guardados y HTML descargable. La cadena embebida explica gran parte del tamaño, no 2779 líneas de lógica Python de dominio. |
| editor/utils/db_import.py | 2904 | Preflight ZIP, modelos/BSON, referencias, medios y publicación; función import_zip_into_database y preflight S4 | **Revisado sin cambio inmediato necesario** en integridad: validar todo antes de publicar, propiedad de ficheros y compatibilidad histórica siguen cubiertos. **Separación posterior pendiente** del plan/preflight/aplicación: no retirar validaciones repetidas en fronteras distintas. Corpus ZIP autoritativo disponible y verificado previamente. |
| editor/utils/db_update.py | 2242 | Dry-run, huella del plan, backup, conflicto explícito y recuperación; apply_database_update y _relationship_issues | **Revisado sin cambio inmediato necesario**: contratos no destructivos y plan obsoleto preservados. Modularización de carga/validación/publicación queda pendiente de un lote específico con sus failpoints; no sustituir compensación de recursos por borrado indiscriminado. |
| editor/cpi/streamlit_page.py | 1707 | Composición CPI, metadatos, regiones e imágenes; tres gestores repetidos en _render_page_editor | **Corregido y verificado** el gestor repetido: 9 caracterizaciones pasan antes; 67 pruebas después. 1485 líneas tras consolidar tres copias, con helpers incluidos. Se mantienen todas las claves, regiones, medios y exportaciones. |
| mathmongo/reading_annotations/service.py | 1682 | Asociaciones de documentos/anotaciones/notas/evidencias y barrera de índices; create/update_note y evidencia exclusiva | **Corregido y verificado** el riesgo nuevo de borrador de nota obsoleto mediante CAS del repositorio y revisión esperada opcional. Mantener las validaciones por tipo de evidencia: son contratos distintos, no duplicación eliminable por semejanza. |
| mathmongo/source_catalog_migration/bootstrap.py | 1635 | Máquina de estados, autorización, invariantes, índices, inserción/reconciliación y reanudación; apply de 486 líneas | **Refactorización pendiente** de comprobaciones de reconciliación repetidas. Las barreras antes de escribir y antes del commit se conservan: inspeccionadas en sus puntos temporales, no son redundantes. Ninguna migración de MathV0 se ejecuta para esta tarea. |
| editor/cornell/streamlit_page.py | 1634 | Editor Cornell, regiones, propuesta de división, branding y exportación | **Revisado sin cambio inmediato necesario**: funciones de región ya separadas y mayores funciones alrededor de 123 líneas. Metadatos similares a CPI son candidato de consolidación; no fusionar modelos Cornell/CPI ni retirar el flujo de overflow por coincidencia visual. |
| editor/concept_linking/linking_wizard.py | 1264 | Selección explícita de concepto/evidencia, etapas UI y recuperación parcial; save_guided_link y _render_stage_two | **Revisado sin cambio necesario en este lote**: creación de blanco y creación de enlace están separadas; conserva un blanco confirmado cuando falla el enlace. La habitación debe reutilizar estas identidades y servicios. Mantener las pruebas de contexto, duplicados y evidencia exclusiva. |
| editor/reading_space/reader_page.py | 1241 | Biblioteca, contexto, posición, vista PDF/web y tabs; navegación pendiente y _render_reading_state_actions | **Revisado sin cambio necesario en este lote**: lector canónico conservado. Integrar entrada desde habitación y retorno con localizador; no crear otro almacén de libros ni ignorar la posición ya registrada. |
| frontend/advanced-reader/src/app/App.tsx | 1227 | Ciclo PDF.js, selección, peticiones abortables, anotaciones y evidencia | **Revisado; extracción posterior pendiente** de estado de anotaciones/posición. Las respuestas atrasadas están protegidas por abort/ciclo de documento y pruebas. No reemplazar este lector por una textura de PDF ni eliminar capacidades por tamaño. |
| mathmongo/source_catalog_migration/apply_safety.py | 1186 | Autorizaciones, backup y comparación de snapshots/planes autoritativos | **Revisado sin cambio necesario**: criterios de seguridad explícitos y modelos inmutables justifican extensión. Se conservan aridad, hashes, decisiones y doble lectura de invariantes. El tamaño no demuestra duplicación peligrosa. |
| editor/source_catalog/edit_source_page.py | 1174 | Edición de Source/Reference, vista previa, plan de borrado y recibo de una escritura | **Revisado sin cambio necesario en este lote**: borrador y vista previa obsoleta son distintos del envío confirmado; wrappers tienen consumidores reales en la navegación. No retirar detección de duplicados ni recibos de rerun. |
| frontend/advanced-reader/src/knowledge-map/component.ts | 1172 | Transporte CCv2, estado, ficha, controles, diálogos y pendientes | **Refactorización pendiente durante integración**: extraer presentación/control sin duplicar Tiptap/MathLive. Borrador, recibo y geometría ya tienen módulos propios; el coordinador aún concentra demasiadas responsabilidades. |
| mathmongo/source_catalog_migration/manifest.py | 1122 | Modelos del manifiesto, identidad, transición y CAS | **Revisado sin cambio necesario**: contrato de reanudación y campos set-once centralizados. La longitud incluye modelos/validadores; no quitar hash, estado o revisión por baja cobertura de una rama. |
| editor/pdf_export.py | 1113 | Adaptación concepto/nota, preparación temporal, diagnóstico y publicación PDF | **Revisado sin cambio necesario en este lote**: compilador compartido con rutas mutables y errores tipados. Conservar formato del PDF y salida atómica; comprobar el mismo documento visual en datos temporales. |
| editor/utils/knowledge_graph_sync.py | 1076 | Normalizar snapshots, reconstruir nodos, aplicar altas/bajas visuales y conservar elementos manuales | **Corregido y verificado** reloj UTC; **conservar** API restante. Una baja de vista no es un borrado de concepto. Pruebas previas y nuevas de identidad/posición se mantienen; no reinterpretar filtros como conjunto completo del mapa. |
| exporters_latex/latex_validation.py | 1046 | Validación, ChkTeX, procesos con timeout, diagnósticos y reporte | **Revisado sin cambio necesario**: procesos como listas de argumentos, sin shell; timeout/decodificación y remapeo de líneas comprobados previamente. No eliminar diagnósticos o fuentes legadas desconocidas. |
| frontend/advanced-reader/src/styles/reader.css | 1008 | Controles, paneles, anotaciones y responsive del lector PDF; paletas raíz y media queries | **Corrección pendiente de tema**: al abrir desde el espacio azul, controles deben usar tokens compartidos sin invertir PDF/imágenes. Conserva geometría/selección PDF.js; revisar contraste renderizado y regresiones del lector. |

## Pruebas propias de más de mil líneas

Se conservan e inventarían por separado: test_source_catalog_backup.py,
test_concept_linking_ui.py, test_source_catalog_migration_bootstrap.py,
frontend/advanced-reader/tests/e2e-runner.mjs, test_reading_annotations_ui.py,
test_source_catalog_migration_production_gate.py, source_catalog_migration_fakes.py,
test_database_update.py, test_source_catalog_migration_cli_live.py,
test_reading_space_ui.py y test_reading_annotations_portability.py.

Responsabilidades examinadas: escenarios de backup/restauración y propiedad de
ficheros; contexto UI y evidencia exclusiva; fallos/reanudación de manifiestos;
lector PDF real; rutas/localizadores; planes obsoletos; CAS y fake BSON con
failpoints. La evidencia anterior incluye su ejecución con el ZIP privado y la
integral de esta continuación. No se suprimen casos para reducir líneas. El fake
compartido se amplió únicamente para interpretar el CAS de documento completo;
rechaza expresiones no soportadas en vez de aceptarlas silenciosamente.

Estado: **revisados, conservar por cohortes de comportamiento**. El runner del
lector admite full/imported con recursos propios; no confundirlo con un segundo
frontend. Si se divide posteriormente, conservar el mismo conjunto de aserciones,
recursos, fallos y ciclo de procesos.

## Generados y dependencias

Los bundles del lector/mapa, el árbol Quarto generado y bibliotecas externas no
participan en el ranking anterior. Se revisan sus fuentes, versiones fijadas,
scripts de construcción, manifiestos y empaquetado. El nuevo bundle MathLive
incluye fuentes locales y tiene muchas líneas físicas generadas: ese crecimiento
se informa separado del código mantenido. Cambiar el hash de un bundle es
regeneración, no una eliminación de funcionalidad ni una reducción de deuda.

Permanecen los motivos históricos de exclusión Sonar, sin ampliarlos. JSON de
configuración, TOML, Makefile, shell y licencias se verifican con sus herramientas
y consumidores; que no aparezcan como incidencias Sonar no acredita su corrección.


## Actualización tras Mathfield y bibliografía

El inventario contiene 320 archivos de código mantenido y 194 archivos de
pruebas/harness en este corte. Hay **21 archivos mantenidos de más de 1000
líneas físicas**. La salida generada y la documentación no forman parte del
ranking de código propio. [CSV completo](CODE_INVENTORY.csv),
[veinte mayores actuales](TOP20_CURRENT.csv) y
[registro de revisión](REVIEW_REGISTER.csv) conservan la clasificación y el estado.
Los hashes describen la instantánea de entrada; el manifiesto no certifica su
propio hash ni sustituye las evidencias de ejecución.

| Archivo actual | Líneas físicas |
|---|---:|
| editor/editor_streamlit.py | 5714 |
| editor/cuaderno_page.py | 4122 |
| visualizations/grafoconocimiento.py | 3670 |
| editor/utils/db_import.py | 2904 |
| editor/utils/db_update.py | 2242 |
| mathmongo/reading_annotations/service.py | 1686 |
| mathmongo/source_catalog_migration/bootstrap.py | 1635 |
| editor/cornell/streamlit_page.py | 1634 |
| editor/cpi/streamlit_page.py | 1485 |
| editor/concept_linking/linking_wizard.py | 1264 |
| editor/reading_space/reader_page.py | 1241 |
| frontend/advanced-reader/src/knowledge-map/component.ts | 1236 |
| frontend/advanced-reader/src/app/App.tsx | 1227 |
| editor/source_catalog/edit_source_page.py | 1192 |
| mathmongo/source_catalog_migration/apply_safety.py | 1186 |
| mathmongo/source_catalog_migration/manifest.py | 1122 |
| editor/pdf_export.py | 1115 |
| editor/utils/knowledge_graph_sync.py | 1076 |
| exporters_latex/latex_validation.py | 1046 |
| mathmongo/reading_annotations/repository.py | 1010 |

reader.css (1008 líneas) sigue revisado en la tabla anterior aunque ahora ocupa
el puesto 21. CPI permanece en 1485 después del lote caracterizado: no se ha
trasladado esa longitud a otro archivo. El coordinador del mapa queda en 1236;
la nueva responsabilidad bibliográfica está separada en bibliography.ts y
DocumentCitation, ambos incluidos en el inventario, sin contabilizarlos como
código eliminado. La responsabilidad del coordinador sigue pendiente de una
separación mayor durante la integración de la habitación.

### Archivo que cruza ahora el umbral: reading_annotations/repository.py

1010 líneas. Contiene repositorios canónicos de anotaciones, notas y evidencia,
hidratación BSON, paginación, búsqueda, archivo/reactivación y joins de evidencia
indirecta. Se examinaron las lecturas ligadas a Source/documento, update_content
para notas, los reemplazos de ciclo de vida y list_by_document con sus joins.
El CAS de nota compara todo el BSON observado y conserva campos desconocidos;
la cita añade un localizador independiente sin reemplazar cuerpo, tags o datos
ajenos. Las regresiones de carrera y persistencia pasan en Mongo standalone propio.

**Decisión:** conservar los contratos y mantener pendiente un lote específico
para separar repositorios comunes y caracterizar carreras de tags/archivo en
los otros métodos. El CAS de edición no demuestra por sí solo concurrencia
segura de cada operación de ciclo de vida. No se eliminan entidades, validadores,
joins ni pruebas para reducir tamaño.


## Corte de habitación: inventario actual y decisiones posteriores

328 archivos de código mantenido y 200 de pruebas, separados de 276 generados.
[TOP20_CURRENT.csv](TOP20_CURRENT.csv) contiene los veinte mayores actuales;
[BATCH4_INVENTORY.json](BATCH4_INVENTORY.json) enumera los veinte propios que
superan mil líneas. Las decisiones anteriores se conservan como historial.

- **component.ts:** refactorización implementada, 927 líneas. Se extraen
  DocumentDialog (398) y map-filters (132); la cuenta conjunta se conserva. La
  reducción del coordinador no se presenta como eliminación neta. Las regresiones
  de borrador, recibo, selección/scroll y pregunta enlazada pasan.
- **bootstrap.py:** predicado de completitud compartido; conserva las cuatro
  reconciliaciones, códigos y checkpoints. 1635 líneas, sin objetivo cosmético de
  reducción. 67 casos caracterizados pasan antes/después; los otros límites de
  autorización/reanudación siguen activos.
- **reader_page.py / reader.css / App.tsx:** se integra el tema mediante un módulo
  CSS acotado y tokens existentes, sin agrandar la hoja principal ni invertir PDF.
  El parser acepta sólo document_id y la opción theme=study; otros parámetros
  arbitrarios siguen rechazados. Lector real y pruebas de URL/verificación pasan.
- **editor_streamlit.py:** incorpora entrada y retorno de habitación; conserva los
  demás consumidores. Su separación por página sigue pendiente con razón concreta:
  falta paridad de medios, metadatos avanzados y exportaciones en el editor nuevo.
- Los restantes módulos grandes conservan las decisiones individuales previas;
  no se cambian a «cerrados» por cobertura o por el Gate.


La huella de los fuentes del corte final corresponde a be6d6c9d. Los CSV se
generan antes de integrar su propia documentación y no constituyen una huella
autorreferente de sí mismos. El adaptador keyboard.ts permanece pequeño y usa
geometría pública; sus pruebas, layouts y cleanup se contabilizan en el lote.
