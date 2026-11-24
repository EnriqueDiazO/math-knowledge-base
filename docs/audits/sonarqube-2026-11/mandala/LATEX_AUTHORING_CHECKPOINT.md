# Autoría LaTeX completa y preferencias Cornell/CPI — 24 de noviembre de 2026

Estado recuperado: `0bae86e1`, árbol limpio, rama
`feature/knowledge-sphere-2026-11`. Se conservan todos los commits anteriores,
la instalación Sonar, las imágenes anteriores y sus evidencias. No push ni merge.
Este informe describe un checkpoint verificable; la migración completa y el
objetivo interno de 95 % siguen abiertos.

## Contrato y carencia corregida

La superficie de fuente anterior era una textarea. Permitía almacenar LaTeX,
pero no equivalía a ACE en ayudas de escritura. Ahora **Fuente LaTeX** abre un
editor completo CodeMirror 6, cargado bajo demanda. Tiptap/MathLive continúan
siendo la modalidad visual, sin otro servicio de guardado ni otro formato
canónico. No se importó otro editor matemático ni código de Matchaio.

Se comprobaron líneas, resaltado, búsqueda y reemplazo, historial de código,
completado de comandos y entornos emparejados, snippets con títulos compatibles,
selección, salto de línea y altura ajustable. Las herramientas visuales se ocultan
cuando se edita fuente; las acciones de guardado quedan fuera del área de código.
El historial de código corresponde a esa instancia; no se promete conservar el
historial de deshacer tras cerrar la aplicación. Sí se conserva la fuente y la
selección/posición del borrador cuando corresponde.

El texto completo entra y sale como cadena LaTeX; CRLF/mezclas y Unicode se
comprueban sin normalización silenciosa. El árbol Tiptap es una proyección,
no HTML documental canónico. Las construcciones que no puede transformar
reversiblemente mantienen su fuente protegida. La edición localizada compara
las regiones no editadas. La exportación reutiliza el compositor real: respeta
preámbulos completos y evita añadir otro documento alrededor. Guardar no requiere
que se pueda compilar; compilar requiere dependencias disponibles en el anfitrión.

Ocho módulos mínimos fijados de CodeMirror/Lezer, MIT, se justifican en
`LATEX_AUTHORING_PLAN.md` y `package.json`. No se añadieron paquetes Python. El
chunk especializado se solicita sólo al abrir Fuente; la prueba real observa
cero solicitudes antes y una después. Tamaño de ese chunk: 367,51 kB sin comprimir,
119,06 kB gzip; no es una promesa de latencia. No se sustituyeron fuentes MathLive.

## Defectos demostrados y regresiones

| Problema | Corrección y prueba |
|---|---|
| Dos ventanas podían compartir el archivo del borrador | Namespace por ventana, propiedad mediante Web Locks; `window.open` copia sessionStorage, por lo que un identificador de sesión por sí solo era insuficiente. Regresión real: guardar en la ventana clonada y recargar la original conserva su texto local. |
| Cerrar la ventana perdía el acceso directo al namespace antiguo | Panel explícito «Recuperar borradores de otras ventanas» por biblioteca/documento. Navegador cerrado y reabierto con perfil temporal real: copiar, recargar y guardar; los archivos originales permanecen idénticos y Mongo no cambia al recuperar. |
| Conflicto sin resolución explícita | Consultar la revisión, archivar el borrador y combinar únicamente campos editados sobre una revisión conocida. Dos ventanas reales, recarga durante el conflicto, título remoto y cuerpo local; guardado posterior deliberado. Borradores antiguos sin instantánea suficiente se conservan y requieren comparación manual. |
| Reintentar una copia pendiente podía crear otro intento | Recuperar mantiene el mismo intento idempotente; prueba del adaptador verifica payload e identificador exactos, sin envío al recuperar. |
| CSS dinámico bloqueado por la política estricta | CodeMirror utiliza una raíz de componente con hojas construidas; Tiptap recibe estáticamente su CSS MIT fijado y desactiva injectCSS. Chrome/Firefox verifican fuentes/gutter, autocompletado accesible y cero infracciones style-src. No se cambió CSP. |
| Diagnóstico genérico de compilación | Mensajes accionables para paquete/clase ausente, entorno o macro no definidos, con log íntegro y fuente conservada. Cuatro regresiones y prueba de error/corrección desde navegador. |
| Cambio de preferencias sobre una instantánea visual atrasada | Se vacía primero el editor imperativo y se aplica una actualización funcional al documento actual. Regresión con texto aún no notificado a React, recuperación y regiones/campos opacos intactos. |
| Listas editoriales sin nombre accesible inequívoco | aria-label explícito; fallo inicial real conservado y recorrido posterior en ambos navegadores. |

La reproducción inicial del borrador clonado corresponde a un **estado intermedio
con modificaciones**, no al HEAD limpio recuperado. Se conserva su bundle y hash
con `worktree_dirty=true` en `clone-before-build/provenance.json`. Los ensayos
fallidos de estilo, accesibilidad y adaptadores quedan separados de los aprobados.

## Corpus inmutable y alcance de compilación

Seis cuerpos reales proceden del ZIP autoritativo abierto sólo para lectura:
`/home/enriquedo/.local/share/mathmongo/backups/mathkb_export_20260712_073927.zip`.
SHA256: `9b8660712171c7ab6db6fb3148deac23921330e1a640615ae6ae36c97e2165c8`.
Cuatro casos son documentos de prueba nuevos identificados como tales.
No sustituyen las entradas históricas. Los cuerpos privados no se versionan.

| Caso | Procedencia / contenido | Líneas reales | PDF con dependencias disponibles |
|---|---|---:|---|
| 1 | Histórico `id_Curves_001`, definición y fórmulas | 45 | Sí |
| 2 | Nuevo, concept/context/definition/remark/reference; definiciones propias explícitas | 32 | Sí |
| 3 | Histórico `id_Curves_017`, demostración y listas | 147 | Sí |
| 4 | Histórico `id_Curves_026`, Punto no helicoidal y Punto helicoidal, TikZ íntegro | 107 | Requiere definiciones originales ausentes |
| 5 | Histórico `id_Definition_LocalMatrixSymbol_001`, matrices/sistemas | 228 | Sí |
| 6 | Nuevo, macros y entorno personalizado | 16 | Sí |
| 7 | Nuevo, PGFPlots y tikz-cd | 20 | Sí |
| 8 | Histórico `IAI_antecedentes_tema`, referencias y acentos | 62 | Sí |
| 9 | Nuevo, preámbulo completo, mathtools, bibliografía y enlaces | 30 | Sí |
| 10 | Histórico `def:EquivalentFormOfSlowOscillationonHalfLine`, demostración extensa | 325 | Sí |

Cada entrada tiene copia 0400, hash, bytes y procedencia en
`evidence/sonar/latex-parity-2026-11-24/corpus/manifest.json`.
`corpus-dependencies.json` registra declaraciones directas y hashes de las
plantillas locales; no pretende ser un lock transitivo de toda la distribución TeX.

**Límite explícito del caso 4:** faltan las definiciones originales de `concept`
y `reference` en las plantillas actuales/históricas disponibles. La entrada se
almacena, recupera y exporta idéntica y el error se explica. Una variante de prueba
con esos dos entornos definidos expresamente compila el TikZ completo, sin cambiar
el cuerpo; no se atribuye ese preámbulo reconstruido al autor ni se guarda encima
del original. Recuperar su preámbulo auténtico sigue pendiente. Nueve de diez casos
compilan directamente con el contexto disponible; no se informa diez de diez.

## Recorridos y Cornell/CPI

Los recorridos A–H comprueban pegar/guardar/releer exacto, edición de una frase,
alternancia fuente/visual/compilado, dos compilaciones TikZ con cambio localizado,
error corregible, reinicio del backend propio, documento visual mixto y conflicto
entre ventanas. Los otros nueve recorridos existentes se conservan. Se añaden
ventana clonada, recuperación tras cerrar navegador, corpus completo y recuperación
tras reiniciar backend: trece cohortes por navegador. Las pruebas usan eventos
públicos de teclado/clipboard del editor; no certifican el portapapeles del sistema
operativo ni sustituyen una validación personal del usuario.

Cornell y CPI comparten ahora la presentación de sus **contratos editoriales
existentes**: pie automático autor/curso/año o texto propio, posición; marca de
agua de texto, opacidad, escala, posición y alcance. Se conserva una marca de imagen
existente y sus campos desconocidos; la selección/sustitución de imagen queda
pendiente. Guardado, revisión, reintento y render siguen en los servicios canónicos.
Ambas familias mantienen sus regiones, modelos, geometría y plantillas distintas.
Las opciones se presentan progresivamente, no como otro formulario general.

Se prueba persistencia/recarga, pie visible en PDF real, LaTeX de las otras regiones,
replay idéntico tras pérdida de respuesta, campos opacos y rechazo de valores
inválidos sin modificar BSON. No se declara completada la familia por este avance.

## Verificaciones y estado de calidad

Resultados finales, identificadores y comparación: `LATEX_AUTHORING_RESULTS.json`.
La integral Python inicial produjo **2218 aprobadas, una fallida y nueve omitidas**:
el test del manifiesto esperaba la lista anterior a CodeMirror. Se actualizó a las
quince dependencias exactas y los diez tests de empaquetado pasaron. Las otras 2218
no se repitieron porque no cambió producción Python tras esa ejecución.
Las nueve optativas se ejecutaron después sobre mongod propio: todas aprobadas.
Consolidado: **2228 pruebas Python distintas verificadas**, sin fallo pendiente;
no se presenta como una única ejecución integral sin fallos. Las nueve omitidas
por defecto son precisamente esas optativas y no un bloqueo del ZIP privado.
Se reutilizan sus cincuenta pruebas históricas, ya ejecutadas con el ZIP disponible.
Frontend: **389 aprobadas, cero omitidas/fallidas**, TypeScript, ESLint sin avisos y
Ruff de los Python afectados. La auditoría npm de dependencias de ejecución
actualizada también registra cero avisos; la imagen anterior 098cab43 conserva su hash. La compatibilidad retenida incluye el recorrido de
habitación Streamlit y las caracterizaciones vigentes. El harness antiguo
`knowledge-map-browser.mjs` aún contiene selectores de textarea anteriores y no se
presenta como una suite vigente aprobada; no se retira ese consumidor por ello.

Todas las escrituras pertenecen a mongod/PID/dbpath y bases UUID propias, XDG,
perfiles de navegador y recursos temporales. **MathV0_writes=0**. El reinicio
comprueba todas las fuentes recuperadas y el hash del estado BSON completo, no sólo
que la página abra. No se modifica ni reinicia la instancia Sonar.

Línea base confirmada: análisis `68db7833-292e-46f7-8b7b-93e7998ded5e`, fuente
`0e08a639`, 76,4 % general / 81,7 % nueva. Checkpoint A procesado:
`65b19e05-cca9-4d10-bab4-2fe22c15cb67`, fuente `c057a3e2`, **76,5 % / 82,0 %**, Gate
OK, nuevas incidencias 0. Cierre final **`05caf8eb-bca8-40dd-a7ef-abaacf2721cd`**, revisión **`24c4e115f782e4aad2f1b89dbfc09af3358fcc29`**,
CE SUCCESS: **76,5 % general / 82,0 % nueva, Gate OK**. Las opciones editoriales
alcanzan 100 % y la fuente especializada 99,2 %. La producción corresponde a
`187a5a9c`; los dos commits posteriores sólo cambian pruebas. Los commits de
documentación posteriores tampoco se atribuyen a una revisión de producción distinta.
No se modifica referencia PREVIOUS_VERSION del 21 de noviembre, perfiles,
exclusiones ni reglas. Gate oficial: cobertura nueva ≥80, duplicación nueva ≤3,
incidencias nuevas ≤0. En el cierre: duplicación nueva 0.08442 %,
incidencias nuevas 0, condiciones nuevas cubiertas 2808/3775 y líneas nuevas
cubiertas 10859/12886. El 95 % interno sigue pendiente: **11 152 observaciones
generales y 2161 nuevas adicionales** a denominador fijo. Hay 2994 observaciones
nuevas sin cubrir; los scripts del frontend explican exactamente 82 (2,74 %).
El resto pertenece a aplicación/servicios y compatibilidad; no se culpa al tooling.
`SONAR_LABEL` sólo etiqueta evidencia, no configura sonar.projectVersion.

El XML Python local mide 36 243/50 520 líneas (71,74 %), con su alcance propio.
Vitest mide 5327/6778 líneas (78,59 %) y la unión real con Chrome 5649/6778
(83,34 %), más 3559/4984 condiciones (71,41 %). Sonar combina su alcance analizado
y sus condiciones; esos porcentajes no son coberturas intercambiables.
El XML comparable Python mide líneas; las condiciones importadas corresponden
al frontend. Vitest y V8 Chrome se unen comprobando hashes de fuente/artefactos/mapas;
Firefox aporta validación funcional. No se atribuye cobertura de paquete a Python
ni se incluyen cohortes fallidas. Repetición: `REPEAT_REACT_ANALYSIS.md`.

## Estructura, distribución y pendientes

`LATEX_AUTHORING_INVENTORY.json` actualiza veinte mayores y afectados. La entrada
principal conserva **21 líneas** y los veinte archivos propios >1000 mantienen
los hashes ya revisados: se reutiliza esa auditoría. Nuevos módulos separan fuente,
carga, estilos, completado, descubrimiento/recuperación, conflicto y preferencias.
ConceptWorkspace tiene 506 líneas y sigue siendo candidato a separar presentación;
no se cuenta como una reducción ficticia. No se retira código de producto.

Diff hasta la revisión funcional `187a5a9c`: mantenido +1425/−57, pruebas +2081/−51;
las 74 líneas del CSS base Tiptap proceden de la dependencia MIT fijada y no son
una nueva implementación propia. Se retiró la textarea sustituida y se adaptaron
sus pruebas/consumidores. Se trasladaron cuarenta líneas de descubrimiento al helper sin interfaz React,
con su importación y pruebas adaptados; el diff bruto incluye ese traslado.
No se comprimieron instrucciones para reducir líneas.
Los bundles generados se publican aparte y sus nombres viejos se sustituyen por
los hashes nuevos; esas bajas no son eliminaciones de funcionalidad.

AppImage funcional del checkpoint: `dist/MathMongo-187a5a9c-experimental-x86_64.AppImage`.
Conserva diecinueve distribuciones Python fijadas, MongoDB y herramientas TeX/sandbox
externos, navegador externo y persistencia XDG fuera del ejecutable. No es autónoma
ni una versión estable. Tamaño 40 114 680 bytes (+241 664 respecto de 098cab43),
SHA256 `90788e8c254872c3ff6eee9d04f01b270b9bee8495febb37685db4fd837c675a`.
Trece cohortes por navegador desde fuente y otras trece desde la AppImage:
reinicio confirmado, cinco notas y veintidós conceptos recuperados, hash Mongo
completo idéntico. La primera prueba de reinicio del paquete encontró una carrera
del harness entre el padre de extracción y su servidor; `fc532315` exige cerrar
el socket antiguo y comprobar un runtime nuevo antes de leer. No se modificó
el paquete para ocultar el fallo. Se conservan las imágenes anteriores, incluida la de
`098cab43`; la intermedia `79ca36f7` conserva el fallo de accesibilidad y no se
recomienda como entrega. Hash y recorridos del paquete final figuran en resultados.

```bash
.venv/bin/python -m mathmongo.advanced_reader --host 127.0.0.1 --port 8766 --database mathmongo_prueba_personal
# Alternativa empaquetada, con MongoDB/TeX del anfitrión:
dist/MathMongo-187a5a9c-experimental-x86_64.AppImage --appimage-extract-and-run --port 8766 --database mathmongo_prueba_personal
```

Abrir `http://127.0.0.1:8766/study`. El ejemplo elige una base distinta de MathV0;
la apertura no prepara índices silenciosamente. Las acciones explícitas conservan
los contratos de preparación existentes.

**Siguiente corte:** medios/asociaciones completos y operaciones de nota completa
Cornell/CPI con referencias compartidas y confirmaciones contextuales; propuestas
de división y adaptador >30 páginas. Después Worklog/Backlog/Weekly/Deliverables y
promociones; continúan administración/transferencias, restauración y pendientes de
Biblioteca/Diario de la matriz. No se han migrado sólo por compartir un listado.
Ninguna página histórica completa queda lista para retirar en este lote.

## Capturas y commits revisables

Capturas reales, zoom 100 %, 1440 px y 480 px, disponibles localmente:

- `evidence/sonar/latex-parity-2026-11-24/checkpoint-final-chrome/latex-source-325-lines.png`
- `evidence/sonar/latex-parity-2026-11-24/checkpoint-final-chrome/latex-source-narrow.png`
- `evidence/sonar/latex-parity-2026-11-24/checkpoint-final-chrome/structured-cornell-editorial.png`
- `evidence/sonar/latex-parity-2026-11-24/checkpoint-final-chrome/structured-cpi-editorial.png`
- `evidence/sonar/latex-parity-2026-11-24/checkpoint-final-chrome/concept-cold-recovery.png`
- Misma selección en `checkpoint-final-firefox`; los recorridos empaquetados
  y sus pruebas de reinicio están en `package-final-{chrome,firefox}`.

Los directorios archivados pueden conservar capturas de fallos anteriores. Sólo
los trece `result-*.json` del mismo run_id y sus logs aprobados se acreditan al
checkpoint correspondiente; no se interpreta una captura antigua como resultado
nuevo. Ninguno de los cuerpos privados, PDFs ni informes de cobertura se añadió a Git.

| Responsabilidad | Commits principales | Regresiones |
|---|---|---|
| Dependencias y fuente completa | fd7bf75c, 834c3a55 | latex-source-editor, latex-source-loader; corpus A–G en ambos navegadores |
| Ventanas, conflicto y recuperación | e16cc870, 8ceba40b, c057a3e2 | concept-recovery, concept-draft-discovery, study-authoring; clon/cierre/H real |
| Diagnóstico y CSP | b1e79de1, c45d4b22 | test_latex_sandbox, source-styles y compilación/error/autocompletado en navegador |
| Cornell/CPI editorial | 5db85b16, 108e3ec6, 7f41ec32 | test_structured_editorial (8), structured-notes y PDFs/recarga en ambos navegadores |
| Legado editorial y entrada numérica | 24c4e115 | structured-editorial (2), sin agregar valores por abrir una nota |
| Usabilidad de fuente | 1053f431 | controles visuales ocultos, guardar sin superposición, zoom y pantallas estrechas |
| Recursos publicados | 187a5a9c y builds precedentes | hashes privados/públicos y trece cohortes por navegador |
| Reinicio de AppImage | fc532315 | socket antiguo cerrado, runtime nuevo, cinco notas/22 conceptos y hash íntegro |

El JSON de resultados conserva el listado íntegro de commits, denominadores,
los veinticinco déficits principales por alcance y métricas de cada módulo nuevo.
