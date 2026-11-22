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
