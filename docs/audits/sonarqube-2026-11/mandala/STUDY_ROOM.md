# Habitación de estudio y continuidad del editor

Corte posterior al anexo, sobre `feature/knowledge-sphere-2026-11`. Se conservan
los commits anteriores y la instalación. No hay push ni merge. La decisión sigue
siendo Streamlit como aplicación y CCv2 para el espacio interactivo; no se crea
una maqueta separada. El anexo está implementado y verificado en
[BIBLIOGRAPHY_ANNEX.md](BIBLIOGRAPHY_ANNEX.md).

## Abrir y usar

1. En Navegación elige **Habitación de estudio**. Su entrada se conserva al
   recargar mediante `?study=1`, sin aceptar bases de datos en la URL.
2. Añade vistas guardadas a la habitación o crea una esfera vacía. No se crean
   conceptos al crear una vista. **Guardar habitación** confirma las referencias
   elegidas y su colocación; moverlas no cambia coordenadas de sus nodos.
3. **General** muestra los recursos y las esferas; el asa **Recolocar** admite
   arrastre y flechas. El libro abre la fuente seleccionada y el papel abre el
   mismo editor de notas. Son accesos alternativos a los paneles directos.
4. Pulsa el nombre de una esfera para enfocarla en mapa expandido. **Comparar**
   permite elegir dos vistas cualesquiera; en ventana estrecha se alternan con
   botones. La selección se comparte por `id@source`. La línea entre esferas y
   la lista de compartidos sólo representan pertenencia, no una relación matemática.
5. Elige una fuente, un pasaje registrado y **Escribir nota desde este pasaje**.
   **Guardar nota** conserva una ReadingNote; no publica un concepto. Una nota
   sin PDF también puede pertenecer a una Source. Las citas separan página
   impresa e índice físico del PDF.
6. En **Incorporar nota como concepto…**, elige destino y, opcionalmente, una
   pregunta explícita. Confirmar usa el servicio canónico y conserva nota,
   anotación y enlaces de evidencia. Guarda después la disposición de la vista.
7. Para pertenencia, usa **Más acciones → Añadir/Quitar concepto seleccionado a
   esta esfera**, y guarda su disposición. Quitar pertenencia no borra el concepto.
8. El editor admite prosa, listas, código, bloques de resultado y MathLive.
   Fracción/matriz/raíz/integral se insertan visualmente. El teclado ofrece
   números, símbolos, letras y griego, variantes, deshacer y rehacer.
   **Fuente LaTeX** sigue disponible; los fragmentos desconocidos se conservan.
9. **Conservar borrador y volver** y **Recuperar borradores** conservan texto,
   selección matemática, desplazamiento y ficha bibliográfica por base/vista.
   Una fórmula nueva incompleta se señala sin bloquear el resto de la prosa;
   se corrige antes de guardar. Los envíos pendientes se reconcilian con el
   mismo identificador; el formulario queda inerte mientras no hay confirmación.
10. **Leer concepto → Fuentes y pasajes registrados** vuelve por los IDs
    canónicos al lector. Si existe anotación, usa su página registrada. Un enlace
    bibliográfico general se presenta como general; no se inventa un pasaje.

## Identidad, persistencia y comprobaciones

RoomVault conserva varias habitaciones locales por base. DraftVault conserva el
mismo documento recuperable; no hay un segundo editor para notas. Las poses de
habitación, cámaras y coordenadas S² de cada vista tienen contratos separados.
Mover cámara/nodos no escribe Mongo: los guardados son explícitos. Source,
Reference, SourceDocument, ReadingNote y ConceptEvidenceLink mantienen sus IDs.
Dos títulos iguales con Sources distintas no se fusionan.

El runner `tests/run_study_sphere_e2e.py --room --browser=chrome|firefox`
crea mongod, dbpath, base, puertos, XDG, Streamlit y lector avanzado propios.
Valida el PID del servidor y elimina únicamente sus recursos. El proveedor de
metadatos simulado y la pérdida deliberada de una respuesta de guardado se
instalan sólo en un wrapper temporal de prueba, nunca en el producto.

Chrome 158.0.8127.36 y Firefox 151 verifican la aplicación real: lector PDF azul,
anotación de página 2/impresa xii, nota con fracción incompleta, recuperación
tras F5 con selección/foco matemáticos, corrección con teclado, respuesta perdida,
reintento sin duplicación, publicación explícita, un concepto en ambas vistas,
comparación a 420 px y vuelta al pasaje después de otra recarga. El escenario
contiene un registro distinto con título e ID legado iguales en otra Source.

El recorrido general del editor comprueba fracción y matriz con el teclado
virtual, cuatro distribuciones, pulsación prolongada/variante, deshacer/rehacer,
DOI sin resultados/indisponible/recuperado, ficha corregida, reutilización de
referencia y conservación de localizadores. Se conserva el cuerpo legado
privado de 12368 caracteres al abrir/guardar sin cambios; no se publica su texto.
Las capturas y registros privados están bajo `evidence/sonar/mandala-2026-11/`.

## Regresiones reproducidas

- La inicialización de contexto S4 borraba la sugerencia de página tras F5: el
  retorno del concepto abría 1 en vez de 2. `study_navigation` valida asociación
  documento/anotación y usa además la cola canónica de Reading Space, que
  sobrevive a ese reinicio. La regresión comprueba que un número recibido del
  navegador no sustituye al de la anotación y que no hay escrituras de navegación.
- El recibo de una vista/habitación podía marcar como guardados cambios locales
  posteriores al envío. Las instantáneas son inmutables y el recibo sólo limpia
  el estado que confirma. Evidencia anterior: dos fallos en
  `room/presentation-regression-before.log`; pruebas corregidas pasan.
- Un recibo tardío podía reemplazar el vínculo ya existente de una pregunta.
  Evidencia anterior: `room/goal-ack-before.log`; se conserva el otro vínculo y
  el concepto confirmado, sin reutilizar el ID de operación para otra escritura.
- Una definición visual nueva sin argumento de título enviaba la primera letra
  del cuerpo al encabezado PDF. Siete regresiones fallan antes. La serialización
  ahora añade `{}` a las siete cajas que lo requieren; proof conserva su
  contrato y los bloques legados mantienen bytes. Se compila el concepto real
  capturado por el navegador, no un cuerpo aproximado. PDF/TeX/imagen antes y
  después quedan archivados. Dos pasadas correctas, con el aviso preexistente
  de compatibilidad siunitx/physics; no se alteran plantillas ni color de exportación.

## Refactorización y retiradas

`component.ts` queda en 927 líneas. Se extraen DocumentDialog (398), que posee
el ciclo del diálogo/Tiptap/MathLive, y map-filters (132), que posee visibilidad
áreas/disposición. Se cuentan ambos: trasladar código no es eliminarlo. La
habitación se organiza en paneles de fuente, nota y preguntas para separar
responsabilidades sin nuevas rutas de persistencia. El inventario cuenta room.ts,
room-state.ts y provenance.ts como código añadido.

Fuera de interfaz, bootstrap comparte el predicado de completitud de catálogo.
Se mantienen sus CUATRO lecturas de reconciliación en tiempos distintos, sus
códigos de error, failpoints, doble snapshot legado y barrera final. No es una
reducción neta de líneas. Las 67 pruebas de bootstrap/production gate pasan antes
y después. La huella histórica se actualiza sólo después de revisar este cambio;
no se debilita la autorización de migración ni se ejecuta una en MathV0.

Se reemplazan los bundles empaquetados por salidas del build con sus licencias.
Sus decenas de miles de líneas son generadas: no se reportan como código de
producto eliminado. No se retiran Cornell/CPI, el lector PDF, el editor avanzado,
medios ni importaciones: conservan consumidores y capacidades que todavía no
tienen paridad en la captura contextual. La matriz anterior sigue vigente.

## Alcances y pendientes reales

- El snapshot de habitación está acotado a 100 Sources y 100 recursos por Source;
  muestra esa limitación y remite a la biblioteca para listas adicionales.
  Falta paginar/resolver individualmente referencias fuera de ese primer lote.
- Las pruebas S²/capas/identidad y las de persistencia se conservan. El registro de
  aceptación distingue las verificaciones unitarias de las del navegador; no se
  infiere una tasa de FPS de los tiempos de dibujo.
- El benchmark comparable usa Chrome 158, 1440×1100, DPR 1, movimiento reducido,
  1003 nodos/1999 relaciones, cinco calentamientos y 20 dibujos. Media anterior
  7,87 ms; nueva 10,56 ms, mínimo 7,40 y máximo 28,90. La medición nueva coexistió
  con verificaciones Python: no permite atribuir causalmente toda la diferencia
  al renderizador. El error de consola corresponde al icono remoto de Streamlit
  bloqueado deliberadamente; cero excepciones de página. No se afirma mejora ni
  FPS sostenidos. Se repitió con las verificaciones y Sonar ya terminados:
  media 8,515 ms, mínimo 6,80 y máximo 12,0 (20 dibujos). Se conservan ambos
  resultados; la diferencia frente al anterior es +0,645 ms de media y no se
  interpreta como una medida estadística de rendimiento sostenido.
- Los 20 módulos propios actuales de más de mil líneas tienen decisión individual
  en LARGE_FILES.md. Los módulos pequeños pendientes siguen explícitos en el CSV;
  un Gate aprobado no cierra esa revisión. Siguen candidatos cuaderno, plantilla
  del exportador PyVis, composición principal y ciclo de anotaciones/PDF.
- El ZIP privado autoritativo está disponible: sus 50 pruebas históricas se
  ejecutan con sus datos originales. No queda ese bloqueo ni se sustituyó el ZIP.


## Cierre de cobertura y Sonar

Análisis final **ce5ea5f2-3ad3-49a8-8da5-9b9c5cadade9**, CE SUCCESS, revisión
**be6d6c9d387dcaa80b612ba0f5f80420fb72bbba**. El Gate es OK: nueva 82,3 %
(mínimo 80), duplicación nueva 0,0 % (máximo 3), cero incidencias nuevas
(máximo 0). General 70,9 %, líneas 71,2 %, duplicación general 1,5 %; cero
bugs, vulnerabilidades, code smells y hotspots abiertos. PREVIOUS_VERSION sigue
en 2026-11-21T16:46:16+0000. Configuración SHA-256 idéntica y perfiles iguales
salvo lastUsed, timestamp que actualiza el servidor. No se cambia exclusión,
supresión, umbral, regla ni versión de proyecto para conseguirlo.

El primer análisis del lote tuvo nueva 81,8 % y Gate ERROR por S2871: faltaba
un comparador explícito al ordenar IDs compartidos. Se usa el compareKeys ya
existente, independiente del idioma de la máquina. No se aplica localeCompare
a identidades canónicas ni se suprime la regla. El análisis final confirma
que el aviso está cerrado. [Primero](BATCH4_RESULTS.json),
[final](FINAL_STUDY_RESULTS.json), [déficit por archivo](FINAL_STUDY_COVERAGE.csv).

El primer XML de la integral nueva tenía 31299/45739 líneas Python, 68,43 %,
frente a 31848/45644, 69,77 %, en el corte bibliográfico acumulado. La mayor
diferencia localizada era editor_streamlit.py: de 574 líneas medidas a cero.
El saldo de los scripts de tooling entre esos XML era cero: no explica la
caída. El informe fresco de pytest no incluía el recorrido de navegador.

Se instrumenta el runner real y sus procesos propios, conserva trazas al cierre
graceful (sigterm) y combina sólo si pasan las pruebas. Tres regresiones nuevas
comprueban éxito, fallo de pytest y fallo de navegador, propagación del código
y limpieza XDG. No se combina una ejecución fallida como si estuviera aprobada.
El comando de Sonar incorpora ahora ese recorrido, con las mismas exclusiones.

Cuantificación del efecto: tras purgar/reverificar los dos scripts modificados,
el reporte previo al navegador tenía 31239/45747. El navegador aporta **790
líneas previamente no medidas**, 540 de ellas en editor_streamlit.py; el resto
son servicios/páginas realmente usados. Reejecutar los 14 contratos HTTP de
Sonar recupera otras 68 líneas del script cuya cobertura se había purgado.
Resultado local final **32097/45747 = 70,16 %**. No son 790 líneas de scripts:
la contribución directa de la entrada principal se identifica por archivo.
Frontend V8: **3473/4396 = 79,00 % de líneas**; los comportamientos JavaScript
del navegador no se adjudican al LCOV de Vitest. Sonar combina lenguajes y
condiciones, de ahí su 70,9 % general y 82,3 % nuevo.

Sonar nuevo: 4845 líneas (679 sin cubrir) y 1594 condiciones (463 sin cubrir),
5297/6439 elementos cubiertos. De los 1142 elementos sin cubrir, sólo **29**
pertenecen a scripts/ (2,54 %); esos scripts tienen 454 líneas nuevas medidas.
Room, coordinador, Canvas y documento explican la mayor parte restante. No se
atribuye genéricamente el déficit a tooling ni se excluye código para ocultarlo.

Python: la integral de este lote pasó con 2050/9 omitidas/0 fallidas; esas nueve
pasan en Mongo propio. Después se añaden tres casos de instrumentación y se
ejecutan 45 casos del tooling y 14 de HTTP. Son repeticiones salvo los tres
nuevos: **2062 IDs Python distintos verificados**, no 2059+45+14. La integral
completa precede al ajuste de los dos scripts; sus módulos afectados se
reverifican con cobertura y el runner real. Frontend: 209/0 fallidas.

Ruff 0.4.10, mismo ruff.toml/alcance: **2155** avisos; los 1437 E101 siguen
perteneciendo al literal JavaScript del exportador PyVis.
[Reglas/consecuencias/prioridad](RUFF_CURRENT.csv). No hay autofix masivo ni
afirmación de que estos avisos son 2155 bugs. Los siete paquetes Python ya
corregidos y el npm 21→0 equivalente se conservan de closure/ENVIRONMENT.md;
los manifiestos no cambiaron en este lote.

Para repetir con referencia validada y navegador propio incluido:

```bash
SONAR_LABEL=study-repeat-20261122 make sonar-scan
```

Requiere el Chrome instalado que usa el proyecto. SONAR_LABEL sólo nombra
archivos de evidencia; no modifica sonar.projectVersion. Los XML y LCOV exactos
y sus hashes se archivan antes del envío. La documentación posterior no altera
los fuentes analizados. La configuración persistente de vm.max_map_count ya
está en /etc/sysctl.d/90-mathmongo-sonar.conf; no hace falta repetir sudo.

Capturas con datos temporales: [habitación](screenshots/room-1920.png),
[comparación estrecha](screenshots/room-compare-420.png),
[lector PDF azul](screenshots/pdf-study-theme.png),
[exportación del concepto visual](screenshots/visual-export.png).

Pendiente observado de presentación en el PDF clásico: un ID interno muy largo
puede desbordar el margen; el cuerpo matemático y la referencia del caso están
completos. No se cambió la plantilla global para resolverlo dentro de este lote.


### Último ajuste visual del Mathfield

La inspección de capturas mostró que la altura fija del contenedor reservaba
espacio de más para el teclado numérico. Se corrige usando `boundingRect` y
`geometrychange` de la API pública instalada de MathLive 0.111.4. No se consultan
selectores internos del proveedor en el adaptador ni el DOM padre de Streamlit.
La altura incluye sólo el teclado activo y nuestro control de cierre; se
restauran layouts y se retiran listeners al cerrar. Una prueba de regresión
falla antes y pasa después; ambos navegadores comprueban las cuatro
distribuciones, que su barra no quede debajo del cierre y que el espacio extra
sea menor de 70 px. También vuelven a pasar variantes, fracción/matriz,
recuperación, citas y conservación del texto legado.

Frontend actualizado: **209 aprobadas**; V8 líneas **3473/4396 = 79,00 %**.
[Captura real del teclado](screenshots/mathfield-keyboard.png). Referencia visual
consultada: [teclado oficial de MathLive](https://mathlive.io/mathfield/virtual-keyboard/).
La aplicación conserva sus tokens azules, cuatro distribuciones y herramientas.
