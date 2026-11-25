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


## E1 — corrección de recuperación bibliográfica y cierre de esta ejecución

`cccfac1f` corrige una pérdida demostrada: elegir una propuesta, corregir el título,
recargar y guardar perdía revista/editorial, BibTeX/procedencia y autores
estructurados. `reference-before.log` muestra la prueba fallida anterior al cambio;
`reference-after.log` y `reference-valid-metadata.log` pasan tras conservar la
propuesta y los campos manuales en un único borrador, con el mismo ID de ficha.
La fecha completa de consulta se conserva si no se cambia el día. Los borradores
manuales v1 sin propuesta siguen siendo válidos. Si el JSON recuperado está dañado,
se bloquea el envío parcial y se ofrecen descarga y reinicio con copia archivada.
La respuesta de una consulta del contexto anterior no se reconcilia en el actual.

Se comprobó HEAD antes de ampliar el contrato del backend: ya comparaba revista,
editorial, volumen, edición, BibTeX y otros campos. No se reimplementó esa protección.
Se añadieron sólo `reference_type` y `year_raw`, cuya omisión permitía anunciar
«guardado» de una petición distinta con el mismo ID. Las dos regresiones fallan
antes (`reference-replay-before.log`) y pasan después, con Mongo temporal y sin
modificar la referencia original. No se convierten en una edición implícita.
`f00aa5ac` publica el frontend y es la revisión exacta del paquete final probado.

Verificaciones acumuladas válidas: **2149 casos Python distintos aprobados,
0 fallidos**: 2133 de integral + sus 9 opt-ins ejecutados aparte + 5 nuevos de
empaquetado + 2 nuevos de reintento. Las 22 pruebas focalizadas de captura/HTTP
incluyen los dos casos nuevos y se solapan con la integral: no se suman otras 22.
**271 casos frontend aprobados**; typecheck, ESLint y builds correctos. Cinco
escenarios en Chrome y cinco en Firefox desde la imagen final, incluyendo
pasaje→nota→concepto→esfera→origen, creación bibliográfica/documental, concurrencia,
compilación sin guardar, exportación e identidad exacta de las cinco copias reales.
Cada informe queda ligado a su run_id y revisión. `MathV0_writes=0`.

| Corte procesado | Revisión | General | Nueva | Gate |
|---|---|---:|---:|---|
| Notas B | 79ed6560 | 73,7 % | 72,7 % | ERROR |
| C recuperado y revisado | 1ea60d06 | 73,9 % | 73,8 % | ERROR |
| Híbrido / primer AppImage | a4f5852c | 74,0 % | 73,9 % | ERROR |
| Final bibliográfico | f00aa5ac | **74,2 %** | **74,5 %** | **ERROR** |

Análisis final **`1c60f417-845f-4b54-aee8-98f7ddd0cb45`**, CE SUCCESS, revisión
`f00aa5ac34fdc2ee39ed7162d034d4286784195a`. Falla sólo cobertura nueva
**74,5 <80**. Duplicación nueva **0,11546 ≤3 %**, incidencias nuevas **0 ≤0**.
No se cambia el periodo PREVIOUS_VERSION `2026-11-21T16:46:16+0000`, perfiles,
exclusiones, supresiones ni umbrales. El falso positivo aislado de S5443 conserva
su revisión documentada; no aparecen incidencias nuevas.

Sonar importó `evidence/sonar/coverage.xml` y
`frontend/advanced-reader/coverage/lcov.info`. El XML procede de la integral,
opt-ins y backend instrumentado anterior aún válido; sólo se purgó la medición
de `bibliography_lookup/capture.py` al desplazar líneas y se reobservó con 22
pruebas. El LCOV final añade **252 líneas y 171 ramas** compatibles observadas en
Chrome a las unidades: **4242/5645 →4494/5645 líneas** y
**2471/3975 →2642/3975 condiciones**. No mide automáticamente el Python empaquetado.
No comparar su porcentaje de líneas frontend con el porcentaje general/nuevo de
Sonar que incluye Python y condiciones, ni sumar contadores no equivalentes.

El déficit restante está localizado en `RECOVERY_FINAL_COVERAGE.csv` (184 archivos
con líneas nuevas). Encabezan relaciones de compatibilidad (402 líneas sin
verificar), mapas heredados (286), room (157 líneas y 100 condiciones), canvas
(65/74) y coordinación del mapa (58/76). Son comportamientos/ramas por caracterizar,
no reportes omitidos ni una atribución genérica a tooling. Siguen pendientes también
mantenimiento, edición/exploración/exportación heredadas. Las pruebas añadidas
validan efectos y preservación; no se excluyen esas páginas para aprobar el Gate.

El paquete final está en **`dist/MathMongo-f00aa5ac-experimental-x86_64.AppImage`**,
39.795.192 bytes, SHA256
`ec8ca4cfacb9a605fbaab4713a0439a550d7236619e322de19d18f99fd472e05`.
Se conservan también las imágenes anteriores y sus evidencias. Se comprueban
PDF con pdfinfo/pdftotext y rasterización inspeccionada; hay capturas amplias y
estrechas reales en `evidence/sonar/packaged-study/{chrome,firefox}`.

El constructor no da por migrada la aplicación completa. Biblioteca todavía
necesita edición/archivo/reactivación y BibTeX; conceptos, borrado contextual,
anotaciones y relaciones requieren cerrar todas sus operaciones; Cuaderno,
Cornell/CPI, medios externos, transferencias y administración mantienen su matriz.
No hay retiradas de compatibilidad autorizadas por estos resultados. El próximo
lote recomendado es edición bibliográfica con CAS y las operaciones de Biblioteca,
en paralelo con caracterización de contratos heredados que concentran el déficit.
La ventana nativa, Mongo gestionado, actualización y otras distribuciones de la
AppImage siguen pendientes. El ZIP privado está disponible; no es un bloqueo.

[REPEAT_REACT_ANALYSIS.md](REPEAT_REACT_ANALYSIS.md) conserva el comando/secuencia
reproducible sin alterar referencia y sin perder cobertura Chrome. El inventario
renovado y las decisiones de los veinte archivos grandes están en
[HYBRID_INVENTORY.json](HYBRID_INVENTORY.json) y [LARGE_FILES.md](LARGE_FILES.md).
Los commits de documentación posteriores al análisis no cambian el código analizado.
Todo queda local; sin push ni merge.

## F — Biblioteca recuperada y validación A (24 de noviembre de 2026)

Reanudación en `feature/knowledge-sphere-2026-11`, HEAD `442aa5a4`, sin AGENTS.md
aplicables. Se conservan `3013ab71`, `eca18756`, `c86992af`, `442aa5a4`. Los dos
cambios pendientes eran legítimos: admisión HTTP de la búsqueda bibliográfica
local y orden del recorrido Biblioteca después de las cohortes anteriores.
`library_bibtex.py` ya estaba confirmado en `eca18756`: no había un tercer diff.
La preparación administrativa de Waveform no se repite ni se modifica.

`db85ec15` completa esas integraciones y corrige una carrera real: cambiar el
filtro de documentos mientras se reactivaba podía consultar antes de la escritura
y conservar una lista vacía. La prueba falla antes (`library-reactivation-before.log`)
y pasa después; el filtro espera la confirmación del backend. `720f8fbf` publica
los recursos React. No se retiró ninguna implementación antigua. Los assets con
hash se regeneraron; no se presentan como código propio eliminado.

La integral recuperada terminó con **2148 aprobadas, 9 omitidas opt-in, 0 fallidas**;
los mismos 9 casos pasan aparte: **2157 casos Python distintos aprobados**.
Frontend actualizado: **282 aprobadas**, ESLint, typecheck y build correctos.
Se conservan las verificaciones de 93 casos focalizados anteriores, sin sumarlos
a la integral. Los seis recorridos combinados pasan en Chrome y Firefox, con
MongoDB/PID/dbpath/XDG propios: lectura, autoría, notas, exportación, cinco copias
históricas exactas y Biblioteca. Esta última verifica creación/recarga/edición,
pérdida de ACK/reintento idéntico, BibTeX selectivo, referencia compartida, PDF,
archivo/reactivación, pasaje→nota→conceptos y ancho de 700 px. `MathV0_writes=0`.
Capturas y resultados: `evidence/sonar/independent-study/{chrome,firefox}/library-*`.
No se importa la cobertura del recorrido combinado fallido anterior.

Sonar procesado sobre `720f8fbf6ceafa204a3f41b1552f46b003707036`: análisis
`cf571842-3656-48db-b967-2ef10505dfed`, CE SUCCESS. General **73,9 %**, nueva
**73,6 %** frente a **74,2/74,5** del corte anterior. Gate **ERROR** sólo por
`new_coverage 73,6 <80`; duplicación nueva **0,10731 ≤3 %**, incidencias nuevas
**0 ≤0**. Referencia PREVIOUS_VERSION `2026-11-21T16:46:16+0000`, umbrales, perfiles
y exclusiones sin cambios. XML regenerado desde integral/opt-ins y backend
instrumentado válido; LCOV de 282 unidades más seis recorridos Chrome con
mapas privados comprobados: **4461/5916→4729/5916 líneas**,
**2683/4281→2870/4281 condiciones**. Son contadores frontend, no porcentajes Sonar.
`LIBRARY_RESULTS.json` y `LIBRARY_COVERAGE.csv` conservan resultado y déficit.
El alcance nuevo exige 925 observaciones adicionales de línea/condición para
alcanzar 80 % sin modificar código. Destacan relaciones heredadas (402 líneas),
Inicio (289), mapas (286), room (157 líneas/100 condiciones). Inicio tenía 59
líneas sin cubrir en el informe histórico: esta pérdida de observaciones tras
regenerar la integral se investigará, sin inventar ni trasplantar hits de líneas
desplazadas. La calidad sigue abierta; el recorrido A funcional permite Cuaderno.

Biblioteca no se declara migrada en su totalidad: borrado físico, sustitución de
versión/reanclado y decisiones avanzadas de fusión conservan sus procedimientos.
No se reconstruye AppImage: el paquete `f00aa5ac` sigue siendo el artefacto
experimental verificado anterior; los recursos actuales sólo se han comprobado
en el servidor React independiente. Se continúa con el núcleo Diario de Cuaderno.

## G — Núcleo Diario de Cuaderno, validación B

`f81f7479` añade actividades HTTP explícitas sobre `latex_notes`. Reutiliza
`MathMongo` mediante un enlace sin inicialización, la persistencia mínima de
Diario, settings/referencias canónicas y el exportador de proyectos existente.
Las listas consultan título/cuerpo, pero sólo devuelven resúmenes paginados; el
LaTeX completo se pide al abrir. No hay una segunda colección ni otro formato
canónico. El `_id` histórico, ObjectId o string, se mantiene; altas nuevas usan
un ID estable por intento, compatible con el CRUD existente y el índice `_id`.

Una única lectura BSON aporta revisión, cuerpo original y predicado CAS. Se
comprueban concurrencia intercalada real, reintento tras perder ACK y no-op sin
materializar defaults. Los metadatos desconocidos, macros, TikZ, medios y ajustes
se conservan; las referencias del catálogo crean snapshots locales mediante el
adaptador de Diario. Modificar el catálogo no reescribe esas citas. Las entradas
Cornell/CPI y formatos desconocidos se rechazan sin convertirlos a texto libre.

La nueva reutilización detectó que `editor.pdf_export` importaba Streamlit al
cargar el exportador de notas: la prueba de arranque con Streamlit bloqueado
falló antes y pasa después de cargarlo sólo dentro de sus cuatro funciones UI.
Las funciones y consumidores antiguos permanecen; no se cambia el compilador
heredado ni se usa desde HTTP. Los nuevos PDFs pasan por `compile_project` y
el aislamiento existente. El bundle conserva `content/body.tex` exacto; `main.tex`
añade los dos cargadores de macros canónicos, sin duplicar documentclass/cuerpo.

`ffeff389` integra el editor matemático existente y `useLocalForm`, con envío
pendiente durable, bloqueo de edición durante el reintento, recuperación de
selección, revisión de conflicto y rebase explícito sólo de los campos cambiados.
El cleanup de una superficie vieja no recrea borradores guardados ni sustituye
el cuerpo remoto durante un rebase. Referencias y metadatos se abren bajo demanda.
El componente común de exportación admite ahora Diario; exporta la versión
guardada y lo indica expresamente. `123ad626` publica los assets. No se crea
un editor alternativo ni se amplía el entry Streamlit de 21 líneas.

Verificación focalizada: **44 Python** de HTTP/Diario/exportación y **57** de
contratos Cornell/CPI/empaquetado (no sumar a integral por solapamiento).
**290 frontend** aprobadas, incluidos 8 casos nuevos de recuperación y conflicto;
ESLint/typecheck/build correctos. Chrome y Firefox pasan creación visual con
fracción y TikZ, pérdida real de respuesta después de persistir, recarga/reintento
idéntico, referencia del catálogo, edición localizada, conflicto entre ventanas,
TEX/PDF, filtro por fuente y nota histórica sintética sin cambios BSON. Se
conserva además el recorrido previo de cinco copias históricas privadas.
Las capturas están en `evidence/sonar/independent-study/{chrome,firefox}/notebook-*`;
los PDFs se verificaron con pdfinfo/pdftotext y rasterización inspeccionada.
Todas las escrituras pertenecen a Mongo/PID/rutas temporales; `MathV0_writes=0`.

La batería integral y siete recorridos instrumentados están en ejecución para
la medición Sonar B. El Gate anterior sigue ERROR; no se lo declara aprobado.
No se reconstruye la AppImage: el artefacto anterior sigue intacto y no contiene
estos cambios. La regresión de arranque verifica el backend nuevo sin Streamlit;
la integración con las 19 dependencias del paquete se revisará sin reemplazarlo.
La familia Cuaderno sigue parcial: eliminación/medios completos, trabajo/tareas,
semanales, entregables, promociones, Cornell y CPI pendientes; no se retiró código.

## H — contratos retenidos, calidad y cierre del lote

La integral B terminó con **2161 aprobadas, 9 omitidas opt-in, 0 fallidas**. Los
mismos 9 casos pasan en la ejecución opt-in, en Mongo/PID/rutas propios.
Las 11 nuevas caracterizaciones se añadieron después de esa colección: su JUnit
no comparte ninguna identidad con los 2170 casos de B. Resultado reunido:
**2181 pruebas Python distintas aprobadas, 0 fallidas y 0 pendientes de ejecución**.
Los 50 casos históricos del ZIP privado están en la integral, no entre los opt-ins;
se usa el ZIP autoritativo ya disponible, sin datos sustitutos. Los focalizados
44/57 se solapan y no se suman de nuevo. Frontend final: **297 aprobadas**,
ESLint/typecheck y builds correctos.

`2d385653` resuelve dos fallos de integridad demostrados con AppTest y Mongo real:

- La confirmación de borrado y los widgets de edición de relaciones usaban el
  índice de fila; filtrar podía transferir el estado a otra relación. Ahora la
  identidad contiene la huella de biblioteca e `_id`. La regresión falla antes y
  pasa después; editar/borrar explícitamente conserva conceptos y LaTeX.
- La exportación masiva pasaba `db.client` a un servicio que consulta colecciones
  de una Database. Se pasa `db.db`, la base seleccionada. La prueba falla antes y
  pasa después: el adaptador conserva la consulta canónica y los cuerpos reales,
  sustituyendo únicamente la compilación por escritura de TEX en el fixture.

Las mismas pruebas comprueban contadores/filtros de Inicio sin escrituras,
creación/duplicación/consulta de mapas sin reemplazar conceptos, selección vacía
de exportación y limpieza con confirmación/respaldo sólo de archivos temporales
propios. Las dos caracterizaciones Cornell/CPI usan sus servicios con Mongo real
y conservan regiones, identidad, origen, metadatos y el recurso utilizado por la
copia cuando se borra la nota original. Son contratos, no una UI migrada.

`4dd413e7` corrige el botón de búsqueda Diario sin `type` explícito detectado por
Sonar y comprueba búsqueda/paginación, alcance por fuente y recuperación de errores.
`147c44c9` añade cinco pruebas de habitación: colección local sin duplicados,
reconciliación del mismo envío, adopción explícita de revisión conservando trabajo,
nota/cita/pregunta al publicar, preguntas resueltas/pendientes y respuesta de
guardado inválida frente a confirmada. No se atribuyen estas unidades a escrituras
reales: sus contratos de dominio/HTTP se verifican por separado. `d12fcb50` publica
los assets; no se cambia un perfil o supresión para resolver la incidencia.

| Corte procesado | Revisión analizada | General | Nueva | Gate / causa |
|---|---|---:|---:|---|
| Entrada válida anterior | f00aa5ac | 74,2 % | 74,5 % | ERROR: cobertura nueva |
| Biblioteca A | 720f8fbf | 73,9 % | 73,6 % | ERROR: cobertura nueva |
| Diario B | 03ee4a3a | 74,1 % | 74,1 % | ERROR: cobertura y un botón sin type |
| Cierre C | a6d77fdb | **76,0 %** | **80,6 %** | **OK** |

B: análisis `44934ef1-546e-490a-ad4f-e2da59ba897b`. Final: análisis
**`b4ddd3bd-402b-4ab7-80b3-df8231fcc998`**, revisión exacta
**`a6d77fdb7fb056e8f225fdc983254926c6b8b9c0`**, CE SUCCESS y scanner exit 0.
Condiciones finales: cobertura nueva **80,6 ≥80**, duplicación nueva
**0,10067 ≤3 %**, incidencias nuevas **0 ≤0**. El resultado B no se borra ni se
presenta como aprobado; su incidencia se corrigió. `LIBRARY_NOTEBOOK_FINAL_RESULTS.json`
y `LIBRARY_NOTEBOOK_FINAL_COVERAGE.csv` conservan métricas y desglose completo.
Los commits posteriores de este cierre sólo documentan el código analizado.

Referencia inalterada: PREVIOUS_VERSION `2026-11-21T16:46:16+0000`. Configuración
SHA256 `84aec1246aae6a1a3949f786449faf9c19a10894cfcb044adcf81866f18f08a6`.
No se cambian umbrales, reglas, perfiles, exclusiones, supresiones ni versión.
`SONAR_LABEL` nombra evidencias y no establece `sonar.projectVersion`. Waveform,
sus tokens, archivos y configuración no se han utilizado ni modificado.

Cobertura nueva final: **9744/11739 líneas** y **2342/3252 condiciones** observadas;
**1995 líneas y 910 condiciones** siguen sin cubrir. General: 41478/54185 líneas y
3093/4461 condiciones. El LCOV frontend local mide otro alcance: unidades
**4703/6085 líneas y 2891/4461 ramas**; tras siete recorridos Chrome válidos,
**4985/6085 (81,92 %) y 3093/4461 (69,33 %)**, con **282 líneas y 202 ramas**
adicionales observadas. Firefox valida comportamiento; no se inventan hits V8
de Firefox. El log final confirma importación de `evidence/sonar/coverage.xml`
y `frontend/advanced-reader/coverage/lcov.info`, sin rutas ausentes.

La regresión A frente al informe histórico no era un reporte rechazado: al
regenerar la integral dejó de estar el suplemento de observaciones de Inicio.
El informe anterior tenía 240/299 líneas; la integral reproducible A/B sólo
10/299: diferencia **230 líneas**, aproximadamente **1,6 puntos** del denominador
nuevo A. No se trasplantan esos hits antiguos. Dos pruebas de comportamiento de
Inicio vuelven a medir **253/299 líneas** sobre el archivo actual. El resto del
déficit procede de ramas/comportamientos sin observar, no de una atribución
genérica a scripts. Los nuevos contratos reducen relaciones de **402 a 52**
líneas sin cubrir, mantenimiento de **118 a 32**, y room de **157/100** líneas/
condiciones nuevas sin cubrir a **54/53**. Mapas, edición/exploración heredadas,
canvas y el coordinador conservan déficit registrado por archivo.

La integral B se conserva para módulos sin cambios. Al corregir relaciones y
exportación se retiraron sólo sus observaciones obsoletas (10 entradas de datos
por módulo) y se midieron completos con las 11 pruebas nuevas, sin eliminar
archivos ni denominadores. Los assets regenerados obligaron a recoger V8 de
nuevo; el merge valida sus hashes y mapas privados. No se unieron recorridos
fallidos ni posiciones desplazadas de archivos modificados. La secuencia completa
reproducible está actualizada en `REPEAT_REACT_ANALYSIS.md` e incluye ya las
caracterizaciones dentro de la integral futura y los siete recorridos.

Chrome y Firefox finales pasan siete cohortes cada uno: lectura/origen, autoría,
notas/concurrencia, exportación visual/mixta, cinco copias históricas reales,
Biblioteca y Diario. Las evidencias tienen run_id y revisión, y registran
`streamlit_imported=false`, `MathV0_writes=0`. No se ha interpretado una respuesta
vacía como éxito. Las escrituras pertenecen exclusivamente a procesos, bases,
perfiles y rutas temporales propios.

La AppImage anterior permanece byte a byte: SHA256
`ec8ca4cfacb9a605fbaab4713a0439a550d7236619e322de19d18f99fd472e05`.
No se reconstruyó ni se afirma que contenga las funcionalidades nuevas. El backend
actual se importa con Python aislado (`-I -S`), sólo el código propio y las
**mismas 19 distribuciones** fijadas para el paquete, sin Streamlit instalado.
Mongo y las herramientas LaTeX siguen siendo externos. No se modifica el sistema
de empaquetado.

Contabilidad desde el HEAD recuperado `442aa5a4`, excluyendo docs/recursos/build:
**1179 líneas añadidas y 37 reemplazadas/retiradas en 19 archivos mantenidos**;
**1570 añadidas y 13 reemplazadas en 9 archivos de pruebas/harness**. Doce líneas
del runner se trasladaron para ordenar las cohortes; no son eliminación. Las
sustituciones de imports, contratos y del placeholder Cuaderno no retiran
capacidades. **No se eliminó ninguna función propia por supuesto desuso**.
No se cuenta la renovación de assets como borrado de producto ni el Diario nuevo
como reducción de código. El entry permanece en 21 líneas y todos los módulos
nuevos cuentan en el inventario; ninguna extracción se oculta en otro monolito.

Pendientes concretos: Biblioteca conserva eliminación física y planes avanzados
de referencias, sustitución/reanclado de versiones y fusión deliberada. Diario
conserva pendientes de borrado, gestión completa de medios y preferencias
editoriales. Worklog/Backlog/Weekly/Deliverables, promociones, Cornell/CPI,
transferencias y administración mantienen las implementaciones antiguas.
Se detecta además que el selector de formato del exportador individual legado
sigue llamando al mismo generador TEX/PDF: se deja para un contrato específico,
sin declararlo corregido por la prueba de exportación masiva. La auditoría de
mantenibilidad continúa aunque el Gate esté OK. No se retira Streamlit.

Siguiente lote recomendado: el corte vertical Cornell definido en
`CORNELL_CPI_NEXT.md`, empezando por CAS estructurado, regiones y overflow antes
de publicar sus acciones HTTP. `PARITY_V014.md` delimita implementado, verificado
sin Streamlit y pendiente/listo para retirar: este lote no autoriza retiradas.
Todo permanece en la rama de desarrollo y en commits locales; sin push ni merge.


## 24 de noviembre de 2026 — Cornell/CPI, Matchaio selectivo y distribución

Se recuperó `278b420c`, rama `feature/knowledge-sphere-2026-11`, limpia. Se
conservan los commits y las verificaciones anteriores válidas. Se consultaron
los modelos/servicios actuales, las implementaciones históricas y el ZIP de
referencia sin sobrescribir el código. La especificación Cornell/CPI previa se
conserva marcada como ejecutada en su núcleo, con pendientes explícitos.

**Migrado y verificado sin Streamlit:** crear/buscar/abrir Cornell/CPI, editar sus
tres regiones independientes, guardar, recuperar tras recargar, gestionar páginas,
citas deliberadas del catálogo y TEX/PDF con estilos y geometría canónicos. Se
reutilizan `latex_notes`, MathMongo, servicios/modelos por familia y el editor
compartido. El adaptador HTTP delimita modelos v1 con 1–30 páginas; las versiones
y documentos históricos fuera de ese límite siguen disponibles por compatibilidad.
Los valores desconocidos y la fuente divergente no se normalizan al abrir/guardar.

Antes de ampliar UI, cuatro regresiones reales demostraron sobrescritura de
fuente/no-op y carrera de actualización. `0707405c` usa snapshot BSON/CAS y cambios
mínimos, compatible con standalone; `4d31109e` corrige el fondo Cornell omitido
en el bundle portable. `ec057832` añade dominio/HTTP y ajuste TeX dentro del
sandbox existente; el overflow y la falta de medición bloquean PDF conservando
fuente/TEX. `c0dbeb22` y `811d112e` publican la actividad React y preservan orden
histórico/campos opacos por página. Replay exacto y confirmación posterior a CAS
impiden falsos mensajes de guardado. Un fallo del registro de medios se repara
por reintento sin retirar referencias ajenas ni borrar bytes.

Matchaio fue inspeccionado en `8194e17` sin modificaciones y probado en copia
independiente (31 pruebas). Se encontró texto LaTeX/KaTeX sobre canvas, no un
editor de subexpresiones equivalente a MathLive. Tras comparar capacidades y
licencias se implementaron tres ideas propias: inserción por selección e historial
de fórmula, paleta de trece estructuras buscables y matrices configurables.
Cero código copiado, cero dependencias nuevas. Se preservan Tiptap, MathLive,
LaTeX canónico, bloques protegidos y los ocho tipos/alias/colores.

`cc4d08fc` corrige `replaceAll` destructivo con regresión antes/después;
`31d99bc9` evita aplicar/anunciar citas atrasadas en otra región; `d7a411e0`
corrige S9011 sin supresión y acota las herramientas también fuera del diálogo.
`0e08a639` refuerza el ensayo A–H: pegado por handler real, fórmula insertada
cuando TikZ ya existe y edición localizada de una copia histórica mediante fuente.
El evento sintético de Firefox necesita payload explícito en el harness; no se
presenta esa diferencia de automatización como fallo del editor ni como prueba
del portapapeles del escritorio.

**Pruebas:** 2200 aprobadas en integral +9 optativas reales +5 regresiones de
confirmación +2 de límite añadidas después = **2216 Python distintas**; cero
fallidas. Las nueve omitidas por la integral se ejecutaron después. Los cincuenta
casos del ZIP privado están incluidos. Frontend **348/45 archivos**, cero fallos.
No se suman ejecuciones repetidas. TypeScript, ESLint y Ruff focalizado pasan.
Se verificaron nueve cohortes por Chrome/Firefox desde fuente y paquete, y
posteriormente el ensayo A–H reforzado. Todas las escrituras en mongod/PID/dbpath,
base UUID, recursos y XDG propios; **MathV0_writes=0**.

Sonar final procesado **`68db7833-292e-46f7-8b7b-93e7998ded5e`**, fuente exacta
**`0e08a639578546f0fbcd5375be299efdffef4163`**, CE SUCCESS. Comparación preservada:
**76,0→76,4 % general**, **80,6→81,7 % nueva**, **Gate OK**, cero incidencias nuevas.
Condiciones: nueva ≥80; duplicación 0,09069 ≤3; nuevas incidencias ≤0. El ERROR
intermedio por S9011 permanece documentado como corregido. Referencia
PREVIOUS_VERSION del 21 de noviembre, perfiles, reglas, umbrales y exclusiones
sin cambios; SONAR_LABEL sólo nombra archivos. La meta interna **95 % sigue
pendiente**: faltan al menos 11 127 observaciones generales/2133 nuevas a
denominador fijo. Seis archivos de tooling explican sólo 98/2934 faltantes nuevos.
La importación XML/LCOV se reconcilia por archivo, incluidas líneas BRDA y alcances
diferentes; no se transfiere cobertura vieja sobre archivos modificados.

AppImage nueva **098cab43**, 39 873 016 bytes, SHA256
`6779d1a5f73655231b5dddf49ef7ed83b5a8a1ee7bf48aaafd768f3e5a5a8631`, +77 824 bytes
frente a la inicial preservada. Mismas diecinueve distribuciones fijadas; MongoDB,
TeX/sandbox y navegador externos. Se arranca desde temporal sin repo/venv/Streamlit.
Tras los nueve recorridos se reinicia sólo el grupo del backend propio y se
recuperan cinco notas con el mismo hash del estado Mongo completo en ambos
navegadores. No se declara autónoma ni versión estable.

La entrada ya tenía 21 líneas y sigue en 21. Los veinte archivos propios >1000
conservan hash/revisión; se mantienen todas sus decisiones y pendientes. No se
retira código de producto. Código mantenido +2154/−29, pruebas +2494/−3 hasta
`9814f890`; el refuerzo A–H añade 54/−4 de harness. Bundles generados se cuentan
aparte. Los nuevos módulos por responsabilidad no constituyen una reducción
ficticia del código ni un monolito trasladado.

**Todavía parcial:** asociaciones/medios y preferencias Cornell/CPI completas,
duplicación/borrado de nota, propuestas de división aceptables, adaptadores para
más de treinta páginas; Worklog/Backlog/Weekly/Deliverables, promociones,
transferencias y administración avanzadas. Biblioteca y Diario conservan sus
pendientes anteriores. Ninguna página histórica queda lista para retirar sólo
por este checkpoint. El próximo lote debe cerrar medios/asociaciones y borrado
seguro Cornell/CPI y continuar tareas del Cuaderno, con pruebas de efectos reales.

Informe y capturas: [CORNELL_CPI_CHECKPOINT.md](CORNELL_CPI_CHECKPOINT.md).
Datos verificables: `CORNELL_CPI_RESULTS.json`, `CORNELL_CPI_INVENTORY.json`.
Decisión Matchaio: [MATCHAIO_REVIEW.md](MATCHAIO_REVIEW.md). Plan 95 y matriz
actualizados. Comandos de cobertura/sonar en `REPEAT_REACT_ANALYSIS.md`; arranque
en el informe y `packaging/react-appimage/README.md`. Commits locales por alcance;
no push, merge, reinicio Sonar, cambio de credenciales ni trabajo sobre Waveform.

## Autoría completa y preferencias editoriales — 24 de noviembre de 2026

Se recuperó `0bae86e1` limpio y se conservó la rama. CodeMirror 6 mínimo y diferido
completa la superficie de fuente: no sustituye Tiptap/MathLive ni LaTeX canónico.
Diez casos (seis históricos, incluido helicoidal y una demostración real de
325 líneas) prueban A–H. Nueve compilan directamente; el helicoidal conserva
exactamente su cuerpo/TikZ, pero necesita las definiciones originales de concept
y reference. Su compilación con un contexto propio de prueba se distingue del
original. No se inventa ni sobrescribe su preámbulo.

Se corrigieron la propiedad de borradores entre ventanas clonadas, recuperación
explícita tras cerrar navegador, resolución de revisión con instantánea, CSS
compatible con CSP sin relajarla y errores de compilación accionables. Cornell
y CPI incorporan pie y marca de texto mediante sus servicios y exportadores.
Las marcas de imagen existentes se conservan; seleccionarlas/reemplazarlas
desde React sigue pendiente, junto con medios/asociaciones completos y notas
completas duplicar/borrar, división y >30 páginas.

Verificación: **2228 pruebas Python distintas consolidadas**; la integral inicial
registró 2218 aprobadas/1 fallida/9 omitidas, después diez de empaquetado pasan y
las nueve optativas pasan con Mongo propio. Se explica el detalle en el informe;
no se presenta una integral limpia inexistente. **389 frontend**, cero fallidas
u omitidas, ESLint/TypeScript y Ruff afectados. Trece cohortes por Chrome/Firefox
desde fuente y otras trece desde la AppImage; recuperación de cinco notas y
veintidós conceptos tras reiniciar sólo el backend propio, con hash Mongo íntegro.
El harness se corrigió para no confundir el servidor que se cerraba con el nuevo.
MathV0_writes=0; el ZIP privado se abre únicamente para lectura.

Sonar procesado `05caf8eb-bca8-40dd-a7ef-abaacf2721cd`, fuente `24c4e115`,
producción `187a5a9c`: **76,4→76,5 % general, 81,7→82,0 % nueva, Gate OK**,
cero incidencias nuevas. Condiciones nuevas 2808/3775, generales 3559/4984.
Ref/perfil/reglas/umbrales/exclusiones/SHA conservados. El 95 % sigue pendiente:
11 152 observaciones generales y 2161 nuevas a denominador fijo; tooling sólo
82/2994 faltantes nuevos. El nuevo componente editorial llega a 100 %; los
coordinadores y deuda heredada permanecen abiertos.

AppImage **187a5a9c**, 40 114 680 bytes, SHA256
`90788e8c254872c3ff6eee9d04f01b270b9bee8495febb37685db4fd837c675a`,
+241 664 bytes respecto de 098cab43; diecinueve distribuciones Python sin cambios.
Mongo/TeX/sandbox y navegador externos, XDG fuera del paquete; experimental.
Imágenes anteriores preservadas; la intermedia 79ca conserva el fallo de
accesibilidad y no se recomienda. No hay retiradas de producto. Entrada 21
líneas y veinte mayores >1000 con hashes anteriores intactos. Descubrimiento
de borradores se separa por responsabilidad; módulos extraídos contados.

Informe: [LATEX_AUTHORING_CHECKPOINT.md](LATEX_AUTHORING_CHECKPOINT.md).
Resultados y commits: LATEX_AUTHORING_RESULTS.json; inventario:
LATEX_AUTHORING_INVENTORY.json. Matriz y comando reproducible actualizados.
El siguiente corte sigue siendo medios/asociaciones y operaciones completas
de nota, después tareas de Cuaderno y administración. No push ni merge.

## Recuperación funcional y suspensión del empaquetado — 24 de noviembre de 2026

Se recuperó **2803cc37 limpio** y se mantuvo la rama. El nuevo inventario contrasta
109 archivos de editor histórico, 156 del actual y 144 módulos de dominio; incluye
controles secundarios/avanzados y operaciones de los módulos poco visibles.
La unidad de progreso es una operación comprobada, no una página ni un widget.
Primera lista: 276; tras incorporar los filtros avanzados omitidos del Diario,
**277**. Sobre igual alcance: **103/277 (37,18 %) → 110/277 (39,71 %)**.
Esenciales: **109/215 (50,70 %)**. Quedan **54 parciales, una implementada sin
prueba completa y 112 ausentes**. Ninguna retirada ni familia declarada completa.
La fila de derechos de Source separa implementación de verificación y evita
confundir su modelo con los metadatos bibliográficos de Reference.

Se implementan siete operaciones: copiar y borrar notas completas Cornell/CPI,
filtrar ambos formatos por proyecto/contexto/fechas y borrar Diario. La copia
nativa anterior perdía fuente histórica y extensiones; dos regresiones fallan
antes y pasan después con copia exacta. Se comparte el helper nativo y se añaden
CAS, recibo de operación standalone e intento durable por biblioteca/nota/revisión.
Se conserva borrador tras respuesta perdida, eliminación efectiva, 404 y recarga;
la limpieza puede reanudarse sin repetir otra eliminación ni publicar el borrador.
Se mantienen referencias compartidas y bytes físicos, incluida la última referencia.

Verificación: **2239 Python aprobadas/9 optativas omitidas/0 fallidas** en la
integral; las nueve optativas pasan separadamente con mongod propio: **2248
pruebas distintas**. El comando exterior largo notificó 143 tras los resultados
y XML; se conserva ese dato, junto con JUnit cero fallos/errores y generación/
validación posterior exit 0. No se transforma ese estado del proceso en fallo
de una prueba ni se presenta una salida exterior cero inexistente. **396 frontend**,
TypeScript/ESLint, Ruff afectado, **catorce cohortes React por Chrome/Firefox**
y una comprobación adicional del consumidor legado de habitación en Chrome.
Dos dobles de prueba se corrigieron para reflejar borrado real y una aserción
ZIP se ajustó a la ruta portable existente; se conservan los registros fallidos.
Sólo observaciones aprobadas y con código/mapas coincidentes entran en LCOV.

El ZIP privado contiene Diario/Cornell, no CPI. El nuevo caso CPI usa fixture
canónico expresamente identificado y recurso compartido real, con exportación
TEX/PDF, SHA de imagen, eliminación de copia y original/otro consumidor intactos.
Los casos históricos, fuente arbitraria/TikZ y recuperación del editor se conservan.
Todos los writes ocurren en Mongo/PID/dbpath/puerto/UUID y XDG propios; MathV0_writes=0.

Sonar **`e6830f9b-bc15-4a3e-a835-7d00d73293c1`**, revisión **`c1a29eb5`**, CE SUCCESS,
**76,5→76,6 % general, 82,0→82,2 % nueva, Gate OK**, cero incidencias nuevas.
Condiciones nuevas **2915/3898**, generales **3666/5107**. Ref/perfiles/reglas/
umbrales/exclusiones/SHA conservados. Faltan **11170 observaciones generales y
2183 nuevas** para 95 % a denominador fijo; tooling **82/3037 (2,70 %)** de las
nuevas sin cubrir. La mejora porcentual no oculta el crecimiento del denominador
ni sustituye la recuperación funcional. XML y LCOV importados; diferencias de
alcance Python y líneas sólo BRDA cuantificadas en el informe/JSON.

Entrada Streamlit **21 líneas**, veinte archivos propios >1000 con hashes
inalterados y revisiones reutilizadas. Nuevo código en módulos pequeños, sin
segundo editor/guardado ni borrado de capacidades. Fuente mantenida +777/−97
líneas; pruebas +1009/−3, bundles +3422/−3421 (Git físico, renombres como baja/alta).
No se interpreta la regeneración de bundles como reducción de complejidad.

Commits: `2478bb7c`, `ec8ddca8`, `7d3ce7dd`, `4af7c176`, `e8203c25`, `25ea2d6f`,
`d0323c75`, `aed9eb5a`, `c1a29eb5`; documentación final aparte. No push/merge.
**Ninguna AppImage nueva construida ni arrancada**. Se conservan artefactos e
infraestructura, la instancia Sonar, credenciales, tokens ajenos y ajuste sysctl.

Informe: [FUNCTIONAL_MIGRATION_CHECKPOINT.md](FUNCTIONAL_MIGRATION_CHECKPOINT.md).
Matriz: [FUNCTIONAL_PARITY.md](FUNCTIONAL_PARITY.md) / FUNCTIONAL_PARITY.json.
Métricas: FUNCTIONAL_MIGRATION_RESULTS.json. Capturas y pruebas bajo
`evidence/sonar/independent-study/{chrome,firefox}`; logs y auditoría bajo
`evidence/sonar/functional-parity-2026-11-24`. El siguiente corte cierra medios,
asociaciones y controles pendientes de las actividades existentes, después las
tareas del Cuaderno. Resto de conceptos/mapas/transferencias/administración sigue
inventariado. El empaquetado espera la paridad acordada; no bloquea migrar funciones.


## Comparación real de navegación y Cuaderno — checkpoint 6a950695

Desde 07ebdd52 limpio se conservaron procesos 8501/8766 y se levantaron copias
coherentes en 35301/56385 con MongoDB/medios/XDG propios. Se grabaron veinte
destinos Streamlit, seis actividades y siete secciones del Diario; se revisaron
fotogramas. Se implementan Worklog, Backlog, Weekly Review, Deliverables y Kanban
sobre sus colecciones históricas. La matriz pasa 110 → **124/277 verificadas**.
Cornell/CPI quedan accesibles; Diario conserva pendientes precisos, igual que
conexiones, transferencias, medios y administración. No se retira Streamlit.

CPI auténtico: cinco capturas y marca de agua corregidas al pasar rutas nativas
a generación y medición. Galería protegida y PDF/TEX después de guardar/recargar;
ZIP recompilado en directorio limpio. Campos conserva SHA LaTeX exacto al editar
metadatos y exportar. Inicio/Biblioteca/lectura se comparan antes/después al
100/70 % nativo; ventana estrecha y navegación por teclado comprobadas.

Python **2256 aprobadas/9 omitidas/0 fallidas**, más **9 optativas aprobadas**;
frontend **406**. Catorce cohortes por navegador sin Streamlit y clips adicionales
de actividades. Sonar final del primer checkpoint: análisis
**36d724af-791c-47f4-9013-c7e7fe16bce8**, revisión **6a950695**, CE SUCCESS,
**76,7 % general / 81,9 % nueva / Gate OK / cero nuevas**. El primer análisis
33c43042 mostró Gate ERROR por 34 avisos (aserciones fuera de casos y dos tipos
de botón); se corrigieron sin relajar controles. Referencia y SHA intactos.
Objetivo 95 % abierto: faltan 11348 observaciones generales y 2396 nuevas a
denominador fijo. Ver NAVIGATION_COMPARISON_CHECKPOINT.md, matriz y LARGE_FILES.md.

Commits: 878116ec, 1b405639, 6aaaaaab, 33c43042, ee275ee3, 6a950695.
Sin push/merge, AppImages o exploraciones nuevas de esfera. El anexo recibido
durante el cierre se trabaja como lote adicional, con sus notas auténticas,
pruebas y análisis propios; no hereda automáticamente el Gate anterior.
