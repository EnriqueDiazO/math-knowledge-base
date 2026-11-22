# Hallazgos y revisión por componente

Cada archivo versionado vigente figura en INVENTORY.csv con método, componente,
hallazgos y límites. El inventario diferencia fuente propia, tests, recursos,
plantillas, documentación y bundles externos/generados. Sonar + AST abarcan todo el
Python propio; TypeScript/ESLint/build abarcan el frontend; shell y plantillas reciben
la revisión adecuada a su formato. Revisión manual en profundidad: fronteras de datos,
identidad, I/O, permisos, ZIP, procesos, API, estado UI y HTML. Esto no equivale a una
prueba formal de ausencia de defectos en todas las ramas ni a ejecución de todos los
scripts docentes con corpus privado.

## Hallazgos confirmados

| ID / prioridad | Ubicación / evidencia anterior | Consecuencia / cambio | Comprobación |
|---|---|---|---|
| A01 P0, datos | concept_repository.insert_concept_with_latex_atomic: catch incluía el primer insert; duplicado borraba el original | Separar el primer insert de la compensación | Mongo standalone: comparar todos los campos y LaTeX antes/después; fallo antes y aprobado después |
| A02 P1, datos | rollback filtraba sólo id/source; reemplazo concurrente se borraba | Compensar exclusivamente el _id insertado y confirmado | Test real de reemplazo entre primera y segunda escritura |
| A03 P1, datos | detach_media_asset_* confiaba sólo en listas inversas | Usar comprobador común de referencias reales en concepts/latex_notes y listas inversas | Dos propietarios concepto/concepto y concepto/nota; última referencia y flag de borrado |
| A04 P2, funcional | Markdown aceptaba referencia de tres campos y accedía a seis | Campos opcionales mediante zip truncado explícitamente, año entero conservado | Entrada mínima, seis campos, fracciones, aligned y BibTeX |
| A05 P1, archivos | crear_qmd derivaba ruta de tipo y no verificaba los descendientes | Rechazar rutas absolutas/../ y symlinks de directorio/fichero | Payloads controlados y ruta legítima conservada |
| A06 P2, validación | YAML safe_load podía devolver None/list/escalar | ValueError temprano si metadata no es mapping | Tres entradas inválidas y control matemático válido |
| A07 P2, UI | miniaturas restringidas se ocultaban después de document_loaded | Aplicar restricción junto con metadata; retirar efecto tardío duplicado | Test de capabilities existente, sin relajar aserciones; 107 tests frontend |
| A08 P2, comandos | make export/grafo apuntaban a scripts inexistentes; export ignoraba separación metadata/LaTeX | Rutas de módulo reales, base explícita, lecturas y destinos controlados | Mongo real: QMD matemático y grafo HTML, snapshot DB idéntico |
| A09 P1, instalación | poetry check --lock fallaba; lock pandas 3 frente a rango <2.4 | Regenerar lock, pandas 2.3.3 y herramientas declaradas | Poetry check y pip check |
| A10 P1, dependencias | npm audit: 21 paquetes afectados; PDF.js/Vite/tooling con avisos | Versiones compatibles fijadas y bundle reconstruido | npm ci/audit, tsc, ESLint, 107 tests, packaging y Chrome |
| A11 P1, dependencias | pip-audit: 146 entradas en 15 paquetes | Correcciones compatibles; permanecen siete paquetes con avisos | Informe sin filtros, límites por mayor/Python en DEPENDENCIES.md |
| A12 P1, verificación | fallo de scanner podía reutilizar report-task previo | Retirar sólo artefacto generado antes de subir y exigir tarea nueva | 1 test fallaba antes; 6 tests de tooling pasan |
| A13 P2, instalación | ZIP extraído con zipfile perdía permisos Unix de helpers del JRE | Conservar modos del ZIP fijado, incluidos jspawnhelper | Extracción limpia, --version y ejecutable JRE comprobados |
| A14 P1, seguridad | cierre mixto </ScRiPt> en JSON y HTML de preview/tooltips sin escape | JSON seguro en scripts y texto HTML escapado, conservando matemáticas | Parser HTML detecta segundo script antes, round-trip JSON y pruebas de PyVis real después |
| A15 P1, funcional | grafo con tipo lista/título None fallaba; fallback sin aristas usaba variable no inicializada; show esperaba template notebook | Normalizar metadata válida, fallback definido y una escritura HTML para Streamlit | Preview y generación real con listas/None, fallo de escritura y HTML resultante |

P0/P1 anteriores afectan integridad, seguridad o disponibilidad; A11 queda
parcialmente pendiente por las restricciones de compatibilidad explicitadas, no
porque un análisis automático no se haya ejecutado.

## Deuda, interpretación y límites conservados

| ID | Ubicación / clasificación | Evidencia y consecuencia | Propuesta concreta / validación pendiente |
|---|---|---|---|
| P01 | Monolitos editor_streamlit.py, cuaderno_page.py, grafoconocimiento.py; mantenimiento | Mezclan UI, persistencia y presentación; la complejidad absoluta es alta | Extraer por flujo sólo con caracterización; evitar reescritura general. Inventario y métricas localizan los candidatos |
| P02 | datetime.utcnow en UI/medios; deuda real | Valores UTC naive usados por formatos legados; aviso S6903 | Política temporal común + corpus con fechas aware/naive antes de cambiar representaciones |
| P03 | schemas.Referencia/RelationEnriched; interpretación S8396 | En Pydantic 2 nullable no implica opcional al construir. El código actual completa los campos y los tests pasan | Decidir si esos campos deben ser requeridos-nullables u omitibles; no relajar silenciosamente el schema |
| P04 | pdf_export._copy_pdf_to_final_path; permiso 0644 señalado por S2612 | Por defecto el directorio XDG es privado; un destino elegido en directorio compartido cambia la exposición | Definir política de exportación privada/compartida y cualificar antes de cambiar permisos observables |
| P05 | ZIP/migración; alcance | 50 tests requieren un archivo privado autoritativo que no está disponible | Ejecutarlos con el mismo ZIP aprobado y hash esperado; pruebas sintéticas, rutas/symlinks, round-trip y tres E2E actuales sí pasan |
| P06 | Compilación LaTeX y regex de import/render | TeX es un compilador local de contenido confiable, no un sandbox. Sonar señala regex potencialmente superlineales | Para contenido de terceros, cualificar aislamiento y límites de tamaño/tiempo. Medir cada patrón con entradas adversarias antes de declararlo seguro o cambiar semántica |
| P07 | interface.py y editor/interface.py, stubs y paquetes sin import directo | Interfaces legadas difieren en campos bibliográficos; posibles consumidores externos/manuales no demostrados | Conservar. No retirar APIs ni dependencias sólo por ausencia de referencias/cobertura |
| P08 | QMD: título repetido | Dos conceptos con mismo tipo/título pueden compartir nombre; refrescar la misma exportación también usa ese nombre | Diseñar identidad estable y plan de compatibilidad de enlaces antes de cambiar nombres de archivo |
| P09 | Atomicidad multi-recurso | Mongo standalone + ficheros permite compensación best effort, no transacción distribuida | Reportar estados de recuperación y usar confirmaciones/documentos de operación si se requiere concurrencia fuerte; no migrar datos en esta tarea |
| P10 | Tooling nuevo de Sonar | Arranque/bootstrap y varias ramas administrativas tienen validación operacional pero cobertura unitario-instrumentada baja | Añadir pruebas de contrato HTTP/lifecycle y fallos de credenciales/daemon; mantener el umbral del Gate |

## Revisión arquitectónica adicional

- CLI/config/XDG: precedencia explícita y rutas mutables validadas; se revisaron
  secretos redactados, bootstrap de índices y guardas de escritura en recursos.
  make run conserva su receta y la selección DATABASE. Los nuevos comandos no
  instancian MathMongo para evitar inicializaciones de índices no solicitadas.
- Catálogo/documentos/anotaciones: repositorios separados, índices declarados,
  servicios con resultados acotados y validación de identidad; UUIDs/IDs legados
  y formatos de portabilidad se conservan. No se aplicó migración a bases del usuario.
- Export/import/update: revisión de nombres ZIP, tamaño/compresión, duplicados,
  symlinks, publicación de blobs, manifiestos, dry-run y comprobación de planes
  obsoletos. Los E2E crean y eliminan sus bases en mongod independiente.
- Streamlit: lectura de navegación, claves de sesión y callbacks; pruebas AppTest
  de Cornell/CPI/conceptos, scope por base y estado de edición. La corrección del
  lector React mantiene preferencias y capabilities sin cambiar su API.
- API del lector: loopback, Host/Origin, JSON y límites de petición; rango PDF,
  MIME/CSP, redacción de errores y rutas de blob privadas. E2E de selección,
  geometría, anotaciones y concepto vinculado aprobados antes y después del round-trip.
- PDF/Cornell/CPI/Quarto: compilación y diagnóstico locales, timeout, imágenes,
  paquetes y branding mediante pruebas existentes. No se modifican estilos docentes
  ni contenido matemático. Recursos y binarios propios/externalizados se inventarían.
- Procesos: argumentos como listas, cierre de clientes, propiedad del PID/grupo,
  reutilización y no terminación de procesos ajenos. El E2E verifica también rechazo
  de una base incompatible y liberación de todos sus puertos.

## Interpretación individual de avisos Sonar

El fichero SONAR_ISSUES.csv registra cada issue inicial/final y su categoría de
revisión. No se marcaron en bloque como falsos positivos ni se alteraron reglas.

- S5332, local_runtime/health.py (dos issues): HTTP sólo puede dirigirse a loopback
  literal/localhost validado y sin credenciales; no es tráfico HTTP remoto. La
  política está respaldada por tests de hosts/puertos/redirecciones.
- S2871, prepare-pdf-worker.mjs:174 y publish-build.mjs:109/124: sort() es intencional
  para nombres ASCII y hashes de inventario reproducibles. localeCompare depende
  de colación y cambiaría el contrato. Se conserva el orden determinista.
- S8495, source_documents/storage._controlled_directory_issues y
  source_catalog/repository.deletion_blockers: devuelven tuplas de cero o un
  diagnóstico; aridad variable es el contrato explícito tuple[str,...].
- S5850, source_catalog/shared._PYDANTIC_INPUT_RE: las alternativas del lookahead
  son dos delimitadores válidos del mensaje; se conservó el comportamiento cubierto
  por tests de redacción. No se convierte automáticamente en error de seguridad.
- S5779 en tests E2E: los catch conservan y vuelven a lanzar el error de cleanup;
  no transforman una aserción fallida en un aprobado. En código de producción son
  invariantes capturados como resultado de error/rollback; queda deuda de convertir
  los assert de validación en excepciones explícitas para soportar python -O.
- S3923 restante en InteractiveGraphManager._apply_style: helper sin llamadas
  actuales y constante FULL_OPTIONS_JSON no definida. Se conserva por falta de un
  contrato externo demostrado; no afecta a la ruta de generación probada.
- S8786 y S6845: requieren cualificación de rendimiento/accesibilidad específica;
  no se etiquetan como falsos positivos sin evidencia adicional.
