# Migración funcional acumulativa — entregas A–E

Se continúa `feature/knowledge-sphere-2026-11` desde `892ddee1`, sin restablecer
commits, push ni merge. El encargo consolidado y el anexo sobre expresividad
LaTeX son criterios de aceptación. Ninguna pantalla heredada se retira en A.

## Referencia conservada

Análisis anterior `7bfb0b4c-d4cd-4de8-a534-807e97244eab`, revisión
`8dbd6234944e6f39cbadf91b59c44b1fb3173ead`: general 73,0 %, nueva 69,7 %.
Gate ERROR: únicamente cobertura nueva < 80 %. Cero incidencias nuevas.
Referencia PREVIOUS_VERSION de `2026-11-21T16:46:16+0000` conservada.
`SONAR_LABEL` sólo nombra evidencias; no cambia `sonar.projectVersion`.
No se alteran perfiles, exclusiones ni umbrales. El inventario anterior de
archivos grandes y deuda heredada continúa vigente; un Gate no cierra esa deuda.

## A — operaciones fundamentales

- `c4f2658c`: adaptadores HTTP tipados de catálogo, documentos y preparación;
  edición que conserva valores nulos, título literal, campos desconocidos y
  citas no modificadas. Source, Reference y SourceDocument siguen separados.
- `e3d4ce72`: páginas React de creación de fuente, captura bibliográfica manual
  o propuesta editable, PDF/web, creación/edición de concepto y relaciones.
  Reutiliza Tiptap, MathLive, DraftVault y operaciones canónicas. El guardado
  recupera su identidad; no abre Streamlit.
- `4a213d04`: medición de los recorridos con mapas privados del mismo JavaScript
  publicado. No se publican mapas ni se añaden dependencias de ejecución.

Los formularios se dividen por actividad, no por colección: SourceForms,
ReferenceForm, DocumentForm, ConceptWorkspace y ConceptRelations. La extracción
ReferenceForm evita una importación dinámica ineficaz. El entry Streamlit
permanece en 21 líneas. No se eliminan datos, documentos ni capacidades legadas.
Los bundles reemplazados son archivos generados, no funcionalidades retiradas.

### Fallos demostrados

1. Un índice no único equivalente que precedía a otro único válido hacía fallar
   la preparación. Regresión standalone falla antes y pasa después:
   `evidence/sonar/fundamental-authoring/equivalent-index-before.log`.
   El helper canónico ahora examina todos los índices antes de declarar conflicto.
   No sustituye ni elimina índices. La preparación es explícita e idempotente;
   permisos/conexión indeterminados no se anuncian como índices ausentes.
2. El cleanup del editor recreaba el intento pendiente después de confirmar el
   guardado y bloqueaba crear un segundo concepto. Chrome lo reprodujo antes;
   `cleanup-reinserts-pending-before.log` conserva la evidencia. La regresión de
   estado y los dos navegadores comprueban ahora crear dos conceptos distintos.
3. El reintento bibliográfico no comparaba URL/fecha de consulta. Se comprueban
   antes de confirmar identidad: un intento con otra URL no sobrescribe la ficha.

### Verificaciones A

Integral Python: **2116 aprobadas, 9 omitidas, 0 fallidas** (2125 casos).
Los nueve opt-in Mongo pasan en su cohorte propia: **2125 casos distintos
verificados**, ocho más que los 2117 anteriores. Los 50 casos del ZIP privado
se ejecutan; no son estas nueve omisiones ni se sustituyen por PDF sintético.
ZIP autorizado: `~/.local/share/mathmongo/backups/mathkb_export_20260712_073927.zip`.
Tras el ajuste acotado del título, cohorte afectada **72 aprobadas** y cobertura
anexada a la integral; no se descarta su medición válida.
Frontend: **233 aprobadas**, typecheck, ESLint y build correctos.
Chrome y Firefox ejecutan A y el recorrido previo de pasaje/nota/publicación con
MongoDB standalone, puertos, PID, XDG y archivos propios; todas las escrituras
quedan fuera de MathV0. También se ejecuta preparación compatible pendiente
sin publicar el borrador. Sólo se simula la excepción de permisos del driver;
no se presenta esa prueba como una instalación real con ACL.
Capturas y resultados: `evidence/sonar/independent-study/{chrome,firefox}/`.

### Instrumentación cuantificada

Vitest mide 3877/5265 líneas y 2194/3633 condiciones. Los recorridos reales
aportan **232 líneas y 137 condiciones adicionales cubiertas**, manteniendo
exactamente esos denominadores: LCOV combinado 4109/5265 (78,04 %) y
2331/3633 (64,16 %). Éste es alcance frontend local, no cobertura Sonar total.

Se exige igualdad SHA256 entre código observado por Chromium, bundle publicado
y bundle con mapas privados; se comprueba también sourcesContent contra los
archivos fuente actuales. Se vacía cobertura antes de cada navegación completa.
Sólo se unen líneas de ejecución existentes en LCOV unitario; condiciones sólo
cuando coinciden tipo y localización AST completos. Los artefactos sintéticos
del minificador no añaden condiciones ni reciben éxitos inferidos de líneas.
`coverage/browser-merge.json`, `lcov-unit.info`, `coverage-browser.json` y los
JSON crudos permiten comprobarlo. Las pruebas unitarias verifican rechazo de
otro build, URLs ajenas y ampliación artificial del denominador.

## Anexo de expresividad LaTeX

LaTeX sigue siendo canónico; Tiptap JSON y HTML son representaciones de edición
y lectura. Debe documentarse por bloque el entorno y argumentos de las plantillas
reales, comprobar el cuerpo exacto guardado y evitar envolturas duplicadas.
Los bloques avanzados protegidos deben poder añadirse a documentos nuevos.
Criterios obligatorios: visual → LaTeX → PDF; histórico → guardar sin cambios
con igualdad exacta; mixto → edición parcial → exportación sin perder TikZ/macros.
No se declara compatibilidad completa ni se inventan entornos que las plantillas
no definan. Cinco ejemplos reales se copiaron por lectura directa, sin construir
MathMongo ni aplicar mantenimiento a MathV0; las copias están protegidas fuera
 de Git y se importarán sólo en el MongoDB temporal del ensayo documental.

## Matriz actualizada

| Capacidad | Implementado | Sin Streamlit comprobado | Retirada legada |
|---|---|---|---|
| Fuente/ref/PDF/web nuevos | Sí; manual y propuestas explícitas | Chrome/Firefox manual/PDF/web, HTTP reintentos | No: BibTeX y gestión completa pendientes |
| Concepto nuevo/leer/editar | Sí; ocho tipos, revisión y borrador | Chrome/Firefox fórmula, recarga, edición; HTTP concurrencia | No: exportación/acciones restantes pendientes |
| Relaciones | Crear y consultar ambos sentidos | Dos conceptos, dirección y tipo persistidos en ambos navegadores | No: edición/eliminación restantes pendientes |
| Esfera y pasaje/nota/publicación | Recorrido previo conservado | Reejecutado con A en ambos navegadores | No: completar todas las acciones del coordinador |
| Notas independientes/búsqueda/conflictos | Parcial | Recorrido de pasaje y pérdida de respuesta sí | No; lote B activo |
| LaTeX legado/TikZ | Preservación protegida previa | Pruebas anteriores; casos reales ampliados pendientes | No; lote C activo |
| UX adaptable | Ancho/estrecho anteriores conservados | A en escritorio; 80 %/mediano ampliados pendientes | No; lote D |
| Cuaderno/Cornell/CPI/medios/import/export/admin/backups | Servicios y legado conservados | Evidencia histórica, no paridad React completa | No; lote E |
| AppImage | Arquitectura compatible, sin SQLite | Paquete experimental pendiente | No |

Sonar A procesado correctamente: análisis `9e85c7f7-d140-4769-bfe8-3c133c4dc1f6`,
revisión `4a213d047dfc37db598712dd1dad9830d7071f6c`. General **73,6 %**
(+0,6 puntos), nueva **72,3 %** (+2,6). Gate **ERROR**: nueva 72,3 < 80;
duplicación nueva 0,12934 % ≤ 3, incidencias nuevas 0. No hay incidencias
activas. Se conserva el mismo hash de configuración y periodo. Resultados y
déficit por archivo en `AUTHORING_A_RESULTS.json` y `AUTHORING_A_COVERAGE.csv`.
El aumento Sonar incluye pruebas y código nuevo además de instrumentación;
no debe confundirse con los 232/137 éxitos de tooling cuantificados arriba.
B–E y AppImage no se dan por terminados con este checkpoint.

## B — notas, citas y revisión coherente

`7e62d95e` conserva exactamente el cuerpo LaTeX de ReadingNote: tanto el modelo
como la operación recortaban espacios/saltos exteriores. La regresión falló
antes y pasa después; conserva la validación de contenido no vacío, tamaño y
NUL. La búsqueda de notas filtra título/fuente/documento antes de paginar y
proyecta sólo metadatos, sin enviar el cuerpo completo en navegación.

`133067bf` añade Crear nota, fuente seleccionable y registro de fuente con
retorno al borrador, referencias/localizadores, búsqueda paginada y accesos a
notas de fuente/documento. SourcePicker compartido permite buscar y recorrer
más de cien fuentes; sustituye la lista truncada del filtro de conceptos y
el selector duplicado de ConceptWorkspace. Las fuentes mantienen su identidad.

La regresión de concurrencia también fallaba antes: una escritura entre el ACK
y el GET de lectura podía hacer que el editor asociara su cuerpo viejo con una
revisión nueva. Ahora compara cuerpo, título, fuente e identidad; conserva su
borrador y revisión, bloquea el envío y ofrece abrir la versión guardada
explícitamente. El rechazo CAS tiene la misma salida y sobrevive a recarga.
No aparece éxito basado únicamente en terminar una llamada. Las evidencias
anteriores están en `fundamental-authoring/note-{latex,readback}-before.log`.

Verificación afectada: **137 casos Python aprobados**, incluyendo modelos,
portabilidad, servicios y HTTP de lectura/notas, catálogo y CAS. Cobertura
anexada a la integral válida. **235 pruebas frontend aprobadas**, typecheck,
ESLint y build correctos. Ruff de todos los Python afectados sin avisos.
Chrome/Firefox vuelven a comprobar A y el recorrido de pasaje; además crean una
nota independiente, citan página 23, recuperan borrador, pierden una respuesta,
reintentan la misma operación y producen una modificación concurrente real vía
el adaptador canónico. El MongoDB temporal exige exactamente dos notas, cita
persistida y texto del segundo escritor intacto. `note-concurrent-readback.png`
y `notes-browser.json` conservan el resultado. MathV0 permanece fuera del ensayo.

Sonar B: análisis `7ffbfd1f-af4a-4c9b-b5d1-fc49cfaa7588`, revisión
`79ed65609e450bac84e70ef46d7fb2726384a83b`. General **73,7 %**, nueva **72,7 %**.
Gate ERROR sólo por 72,7 < 80; duplicación nueva 0,12858 ≤ 3, incidencias nuevas
0, ninguna activa. Misma referencia/perfiles/exclusiones. Los recorridos aportan
257 líneas y 171 condiciones cubiertas adicionales sobre 5297/3716 del alcance
unitario; son totales de instrumentación acumulada, no incremento exclusivo de B.
`NOTES_B_RESULTS.json` y `NOTES_B_COVERAGE.csv` permiten localizar el déficit.
No se retiran flujos legados. Exportación de notas, vinculación adicional y las
capacidades de E siguen pendientes de paridad, aunque el recorrido de lectura,
nota, incorporación explícita, esfera y retorno ya se verifica sin Streamlit.

## Reanudación del 24 de noviembre — cierre documental C

Se preservaron las 74 rutas pendientes: 46 manuales y 28 generadas. El estado
inicial, procesos y límites de reutilización se registran en
[RECOVERY_2026-11-24.md](RECOVERY_2026-11-24.md). Los cambios quedaron en commits
locales por alcance: `8d3f672b` (citas), `50860f12` (servicio/exportación/aislamiento),
`d8eed079` (editor), `26943c93` (regresiones), `fe1d9fd9` (publicación generada).
No se restauró código ni se copiaron fuentes de la versión histórica.

La reanudación encontró una regresión real de integración: el PNG existía pero
el navegador bloqueaba el blob de la imagen. La prueba anterior de presencia
no demostraba píxeles visibles. `5acbc7d9` conserva CSP y presenta PNG data:;
`a7e0cd50` registra resultados por ejecución y fallos explícitos; `18d2f49f`
publica el arreglo. Las capturas antiguas rotas se preservan como evidencia
anterior, no como éxito visual. Chrome y Firefox vuelven a aprobar los cinco
recorridos, incluida la imagen decodificada/ampliada, además de fuentes, notas,
conflicto, exportación visual/mixta y cinco cuerpos históricos SHA256 idénticos.

Verificación actualizada: **419 pruebas Python** de las fronteras/servicios
modificados y sus consumidores; **256 frontend**, typecheck, ESLint y build.
La prueba de aislamiento reforzada exige EROFS y vuelve a aprobar sus 4 casos.
Los 20 archivos mantenidos de más de mil líneas conservan exactamente su hash:
se reutilizan sus revisiones, sin dar por resueltos sus pendientes. Inventario:
420 mantenidos, 232 pruebas, 313 generados. El entry sigue en 21 líneas;
`document-editor.ts`, 609. Se cuentan todos los módulos extraídos y añadidos.

Se retiraron mediciones antiguas sólo de siete módulos Python modificados,
conservando las del resto. No se unieron números de línea desplazados. La cohorte
419 los mide de nuevo. Los recorridos con backend instrumentado añaden **94
líneas observadas** en seis módulos sobre esa cohorte. No se importan las
mediciones de los recorridos fallidos. Vitest más Chromium aporta **279 líneas y
191 condiciones adicionales**, con denominadores intactos: 4440/5608 líneas
(79,17 %) y 2555/3909 condiciones (65,36 %), alcance frontend local.

Sonar revisado: análisis `2a2fef59-1391-4c2f-ade9-7271eec9e513`, revisión
`1ea60d061c6eb607a4582d554aa9f95e4bbe4fd9`, CE SUCCESS. General **73,9 %**,
nueva **73,8 %**. Gate **ERROR** sólo por 73,8 < 80; duplicación nueva 0,11802 ≤ 3,
incidencias nuevas 0. La clasificación individual S5443 se justifica en
[S5443_SANDBOX_REVIEW.md](S5443_SANDBOX_REVIEW.md): el literal es destino de un
montaje de sólo lectura del namespace, no una carpeta pública de salida.
No se cambia perfil, regla, exclusión, periodo ni umbral. `RECOVERED_C_RESULTS.json`
y `RECOVERED_C_COVERAGE.csv` conservan métricas y déficit por archivo.

[DOCUMENT_CONTRACT.md](DOCUMENT_CONTRACT.md) distingue nodos, fuente almacenada,
serialización, reconstrucción, PDF y límites visuales. [PARITY_V014.md](PARITY_V014.md)
separa lectura, creación, edición, eliminación, validaciones y exportación con
referencias a v0.14.0. No se declara terminada la migración de Biblioteca,
Cuaderno, Cornell/CPI, medios, administración ni la retirada de Streamlit.

## D — borrador compilado, PDF académico y primer paquete experimental

- `d67b7f6b`: compilación de la instantánea aún sin guardar y IDs técnicos
  optativos; dos cuerpos de exportación repetidos pasan a usar el canónico.
- `07a84c9c`, `b62889bf`: integración React y recursos publicados; el texto visual,
  fuente completa y vista compilada comparten el mismo LaTeX.
- `13f0b7cd`, `11dfe468`: constructor y primer AppImage; se corrigió la ausencia
  del pyproject que necesita recuperar la versión. `12811a1c` cierra descriptores
  y prueba publicación/no sustitución; no cambia el payload empaquetado.

Batería integral: **2133 aprobadas, 9 omitidas por opt-in, 0 fallidas**. Los mismos
9 casos pasan bajo `quality_mongo` con procesos/bases propios; se solapan con las
9 omisiones, no son otros nueve tests. Las 5 nuevas pruebas de empaquetado se
crearon después de la colección integral y pasan aparte: **2147 casos Python
distintos aprobados** al reunir ambas ejecuciones y el opt-in. Los 50 casos del
ZIP privado ya forman parte de la integral y no están entre esas omisiones.
Frontend: **258 pruebas aprobadas**, typecheck, ESLint y ambos builds correctos.
Los cinco escenarios independientes pasan en Chrome y Firefox; el paquete
repite esos cinco escenarios en ambos navegadores, con MongoDB temporal real.
No se agregan esos escenarios a la cifra de pytest ni se atribuye cobertura
Python automática al intérprete empaquetado sin instrumentation.

Sonar procesado: `dc70ca8e-4726-4d2c-8c70-1c19ace3ed4c`, revisión
`a4f5852c6197185fa548e7440597fce1b5da810f`. General **74,0 %**, nueva **73,9 %**
(frente a **73,9 / 73,8** del C revisado). Gate **ERROR**, sólo `new_coverage <80`.
Duplicación nueva **0,11604 % ≤3**, incidencias nuevas **0 ≤0**. Referencia
PREVIOUS_VERSION `2026-11-21T16:46:16+0000`, perfiles, exclusiones y umbrales
sin cambios. `HYBRID_RESULTS.json` y `HYBRID_COVERAGE.csv` guardan el resultado
procesado y las contribuciones por archivo. Los principales déficits heredados
siguen en páginas extraídas de relaciones, mapas y mantenimiento, además de
ramas de coordinación del frontend: no se atribuyen a scripts de forma genérica.

LCOV: **4180/5626 líneas y 2383/3933 ramas** de unidades → **4457/5626 líneas y
2573/3933 ramas** después de unir únicamente observaciones Chrome con mapas
privados y denominadores compatibles: **277 líneas y 190 condiciones** añadidas.
Python se regenera desde la integral y opt-ins, más backend instrumentado de ambos
navegadores; se miden por separado los ensayos del constructor actual. No se unen
contadores antiguos de líneas desplazadas ni ejecuciones fallidas del paquete.

El entry sigue en **21 líneas**. `editor/pdf_export.py` baja de **1115 a 1052**,
`ExportadorLatex` de **259 a 216**: presentación de cuerpo/cita/comentario/ID
reutilizada, con todos sus consumidores conservados. El renderizador común
pasa de 567 a 569 y el editor común de 609 a 616: se cuentan también los módulos
reutilizados y los nuevos, sin presentar traslado como eliminación. Las pruebas
siguen comprobando citas ampliadas, rutas XDG, plantillas, compilación y errores.
No se retira ningún flujo, dato, referencia, documento o prueba.

La imagen experimental probada pesa 38 MiB; su contrato y comandos están en
`packaging/react-appimage/README.md`. Depende de MongoDB instalado y herramientas
LaTeX del host. No gestiona un daemon ni acredita portabilidad a otros sistemas.
Sigue pendiente la gestión de Biblioteca y la paridad de Cuaderno/Cornell/CPI,
medios externos, transferencias y administración. El inventario continúa activo.
