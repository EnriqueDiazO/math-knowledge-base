# Recuperación funcional React — 24 de noviembre de 2026

## Estado recuperado y alcance

Se continúa en `feature/knowledge-sphere-2026-11` desde **2803cc37**, con árbol
limpio al comenzar. Se conservan todos los commits y capacidades anteriores.
No push, merge, reset, retirada de páginas ni migración de datos del usuario.
LaTeX sigue siendo canónico y no cambia el editor ni la paleta matemática.

Se suspende construir y probar nuevos paquetes AppImage. Se conserva el artefacto
experimental `dist/MathMongo-187a5a9c-experimental-x86_64.AppImage`, con SHA256
`90788e8c254872c3ff6eee9d04f01b270b9bee8495febb37685db4fd837c675a` y su infraestructura.
Ese binario no incorpora automáticamente este lote. No se ha reconstruido ni
arrancado durante este checkpoint. La batería Python conserva sus pruebas de
contratos del builder; no equivale a probar otra AppImage.

## Inventario y porcentaje verificable

[FUNCTIONAL_PARITY.md](FUNCTIONAL_PARITY.md) y FUNCTIONAL_PARITY.json registran
cada operación, prioridad, estado, servicio, superficie React, pruebas y pendiente.
Se contrastaron 109 archivos Python del editor histórico, 156 del actual y 144
módulos de dominio/persistencia/exportación/parsers/visualización. Los 1081/1055
controles encontrados incluyen pestañas y acciones avanzadas; no se convierten
mecánicamente en operaciones migradas. El ZIP histórico se abre sólo en lectura.
Las versiones, hashes y ubicaciones se conservan en el inventario y en
`evidence/sonar/functional-parity-2026-11-24/{source-audit,ui-controls,service-inventory}.json`.

El primer catálogo contó 276 operaciones. Se añadió un pendiente omitido de
Diario: filtros de contexto/etiquetas/fechas/año/mes/recientes. El catálogo vigente
cuenta **277**, sin renumerar las anteriores. Sobre igual alcance, el avance es
**103/277 (37,18 %) → 110/277 (39,71 %)**; esenciales **102/215 (47,44 %) →
109/215 (50,70 %)**. El primer porcentaje publicado de 103/276 = 37,32 % queda
como historial; no se oculta el nuevo pendiente para mejorar la cifra.

Cierre: **110 verificadas, 54 parciales, una implementada sin prueba completa,
112 ausentes y cero retiradas**. La fila de derechos de Source distingue campos
ya implementados de evidencia de navegador aún pendiente; título/autores
bibliográficos pertenecen a Reference. Paridad funcional y cobertura Sonar son
mediciones independientes. No se presenta una familia completa por tener una
página React.

## Operaciones recuperadas

| Operación | Contrato y resultado | Commits de implementación | Regresión |
|---|---|---|---|
| Copiar nota completa Cornell y CPI | Conserva fuente exacta, estructura y extensiones desconocidas; identidad nueva y asociación de recursos, con reintento del mismo intento | ec8ddca8, 7d3ce7dd, 4af7c176 | test_note_lifecycle_contracts.py; test_note_actions_http.py; note-actions-browser.mjs |
| Eliminar nota Diario, Cornell y CPI | Confirmación por título/identidad/revisión y contexto de biblioteca; CAS sobre snapshot; conserva conceptos derivados, referencias y bytes compartidos | ec8ddca8, 7d3ce7dd, 4af7c176 | HTTP: tres formatos, concurrencia, referencias, fallos parciales y alias BSON; navegador: confirmación y respuesta perdida |
| Filtrar Cornell y CPI | Proyecto/contexto exactos e intervalo de fechas, validación HTTP, BSON datetime y fechas históricas; filtros en URL que sobreviven a recarga | 7d3ce7dd, 4af7c176 | test_note_actions_http.py y Chrome/Firefox |

Son siete operaciones esenciales de la matriz: `diary-20`, `cornell-03/14/15`
y `cpi-03/14/15`. Se accede por Cuaderno → Diario/Cornell/CPI → nota →
«Gestionar esta nota», o «Filtrar notas» en el listado. No requieren Streamlit.
No se retira su consumidor legado ni se considera terminado todo Cuaderno.

### Defecto histórico demostrado

`duplicate-before.log`: las dos nuevas regresiones de copia fallan antes de
modificar producción, en base `2478bb7c`; regenerar la proyección pierde fuente
original y metadatos opacos. Después pasan junto con los contratos existentes.
La copia ahora usa el registro persistido, no la proyección visual. Excluye sólo
identidad, timestamps/seed de origen y marcadores de intentos de creación/edición/
copia anteriores; el nuevo título es deliberado. El resto, incluidas extensiones
anidadas y LaTeX desconocido, permanece idéntico. No se inventan macros.

### Borrado, recursos y fallos parciales

Se reutilizan los servicios Cornell/CPI y el registro de recursos existentes.
`editor/notebook_lifecycle.py` reúne copia y borrado; el facade añade borrado por
snapshot BSON. La consulta no oculta fallos de conexión/permisos como inexistencia.
Se prueban incluso identidades ObjectId y string con el mismo texto, conservando
la otra entidad y su asociación al recurso.

El despliegue real permite MongoDB standalone: no se exigen transacciones. La
operación HTTP conserva un recibo en `study_note_operations` antes de eliminar,
verifica el resultado en backend y permite completar sólo su limpieza tras un
fallo. Una respuesta perdida puede dejar la nota ya eliminada; recargar devuelve
404 y la misma solicitud durable permite terminar sin anunciar éxito inexistente.
Se elimina el snapshot privado del recibo al completar o detectar conflicto;
queda el recibo mínimo para no repetir una eliminación diferente. Un conflicto
exige revisar la nueva versión; no se actualiza silenciosamente la revisión.

La limpieza sólo retira la referencia de esa nota. No elimina ficheros físicos,
ni siquiera al desaparecer la última referencia: conserva el contrato de
administración explícita de recursos. Examina imagen de región, comandos inline,
marca de agua y `image_ids`; la sincronización usa su unión. El borrador local no
se publica, se conserva y puede descargarse independientemente del documento.

## Verificación y compatibilidad

Las escrituras usan mongod propio, PID/puerto/dbpath verificados, bases UUID,
XDG y medios temporales. Nunca se conecta MathV0 para escribir ni se restaura el
ZIP sobre ella. El ZIP autoritativo se lee desde
`~/.local/share/mathmongo/backups/mathkb_export_20260712_073927.zip`.
Contiene 27 notas libres, siete Cornell y **ninguna CPI**. La prueba nueva emplea
una Cornell y un Diario reales copiados a la base temporal; CPI se identifica
como fixture canónico propio, sin atribuirle procedencia histórica privada.

La prueba real duplica Cornell/CPI, pierde la primera respuesta y repite el
mismo intento tras recargar; exporta una copia CPI con imagen compartida a TEX
y PDF, verifica SHA de los bytes exportados y elimina sólo la copia. Luego
comprueba el original íntegro, las referencias del otro consumidor y los bytes.
El Diario conserva un borrador no guardado a pesar de borrado efectivo/respuesta
perdida/404/recarga/reintento. Los filtros se aplican y sobreviven a recarga.

Los fallos de la primera integral se conservan como evidencia: dos dobles del
borrado no retiraban la nota al devolver éxito; se corrigieron para representar
la poscondición real, manteniendo el rechazo de cantidades anómalas. En navegador
se corrigió una expectativa de ruta interna del test: el ZIP portable almacena
`images/note-actions.png`, no `cpi_assets/media`. No se cambió el exportador para
satisfacer esa suposición. Los recorridos fallidos no entran en el LCOV final.

Resultados definitivos y Sonar: véase FUNCTIONAL_MIGRATION_RESULTS.json y el
cierre procesado que sigue. Los informes/XML/LCOV y sus hashes están registrados.

Capturas reales, Chrome y Firefox, con contexto temporal:

- `evidence/sonar/independent-study/{chrome,firefox}/note-copy-cornell.png`
- `evidence/sonar/independent-study/{chrome,firefox}/note-copy-cpi.png`
- `evidence/sonar/independent-study/{chrome,firefox}/note-delete-recovery.png`

Los cuerpos privados, bases, ZIP/PDF de prueba y credenciales permanecen fuera
de Git. Las capturas y evidencias locales se conservan en el directorio ignorado.

## Arquitectura, compatibilidad y código retirado

La entrada Streamlit permanece en **21 líneas**. Los veinte archivos propios
mayores de mil líneas tienen el mismo hash que la revisión anterior: se reutilizan
sus decisiones de LARGE_FILES.md. El nuevo coordinador de aplicación de acciones
tiene 154 líneas; helper compartido 64; modelo HTTP 28; componente React 254 y
estado puro 75. No se crea un segundo editor ni una segunda persistencia de notas.
La confirmación/reintento local usa el almacenamiento y contexto ya existentes.

Código **añadido**: coordinador idempotente, payload HTTP, estado/acciones React
y pruebas. **Consolidado/sustituido**: los dos caminos nativos de copia/borrado
usan un helper común; no es un traslado literal sin cambio, pues se corrige el
contrato de copia y se verifica el borrado. **Eliminado funcionalmente: nada**.
Se sustituyó en Ajustes un aviso fijo Gate ERROR que ya no describía el servidor;
la interfaz no pretende consultar Sonar ni promete un Gate estático aprobado.
Los bundles generados se publican en un commit propio; sus líneas no se cuentan
como reducción de código mantenido ni como funciones nuevas.

## Pendientes y siguiente corte

La matriz mantiene 167 operaciones sin verificación completa; no se omiten al
terminar este lote. Antes de iniciar más módulos, cerrar medios por región y
marca de agua de imagen, asociaciones documentales/bibliográficas completas y
filtros/ajustes pendientes de Diario, Cornell/CPI. Conservar los servicios y
fortalecer sus contratos antes de publicar upload/borrado físico de recursos.
Después, Worklog/Backlog/Weekly/Deliverables/Kanban: extraer sus reglas embebidas
en `cuaderno_page.py`, no generar formularios automáticamente desde MongoDB.

Siguen pendientes operaciones de metadatos de conceptos, relaciones/mapas,
constructor, importación/exportación masiva, respaldos/restauración, bibliotecas
y mantenimiento. Las superficies legadas siguen disponibles para ellas.
Ninguna página ni servicio está autorizado para retirada por este checkpoint.
El objetivo de cobertura 95 % continúa en paralelo, sin postergar estas operaciones.

## Arranque y repetición

Desde el repositorio, con MongoDB/TeX disponibles:

```bash
.venv/bin/python -m mathmongo.advanced_reader \
  --host 127.0.0.1 --port 8766 --database mathmongo_prueba_paridad
```

Abrir `http://127.0.0.1:8766/study`. El comando conserva la arquitectura existente;
no inicia Streamlit ni genera una AppImage. Para pruebas automatizadas usar el
runner aislado, no apuntar la base habitual. Comandos de cobertura y análisis:
[REPEAT_REACT_ANALYSIS.md](REPEAT_REACT_ANALYSIS.md), misma referencia/perfil/reglas/
exclusiones/umbrales. `SONAR_LABEL` nombra evidencias, no cambia projectVersion.

## Cierre procesado de pruebas y Sonar

- Python: **2239 aprobadas, nueve omitidas optativas, cero fallidas/errores** en
  la integral, comprobado también en JUnit; las nueve optativas pasan después
  con mongod propio. **2248 pruebas distintas aprobadas**, sin omisiones pendientes
  de ese conjunto. Se añaden 18 regresiones HTTP y dos nativas; no se suman las
  repeticiones focalizadas al total. Las 50 antiguas dependientes del ZIP ya no
  están bloqueadas. Nueve warnings existentes (Pydantic/adaptador de test HTTP)
  permanecen como avisos, no como pruebas fallidas.
- El comando exterior largo notificó salida 143 después de imprimir ambos
  resultados y escribir XML. No se oculta ni se presenta su código como cero:
  el JUnit de la integral tiene cero fallos/errores y la integración separada
  también termina con nueve aprobadas/exit 0. Combinación, XML y validación de
  informes se completaron después con exit 0. No se volvió a ejecutar toda la
  batería para sustituir evidencias válidas por un estado del proceso exterior.
- Frontend: **396 aprobadas en 52 archivos**, cero fallidas/omitidas; TypeScript,
  ESLint, build publicado y Ruff de los archivos afectados. Siete pruebas nuevas
  verifican la confirmación, reintento durable, cuota/corrupción local, conflicto,
  identidad/contexto y respuesta inválida. No se alteraron dependencias.
- **Catorce cohortes React por Chrome y Firefox**, con las cuatro de autoría
  conservadas y la nueva gestión de notas. Lectura base se repite al dividir
  cohortes, pero no se duplica su crédito. Una comprobación adicional del flujo
  legado de habitación en Chrome pasa con proceso/base propios; no es dependencia
  del recorrido React. Se mantienen los tres contratos de LaTeX: nuevo→TEX/PDF,
  histórico→no-op idéntico y edición mixta con segmentos protegidos.

Análisis **`e6830f9b-bc15-4a3e-a835-7d00d73293c1`**, CE **SUCCESS**,
revisión **`c1a29eb5353ef6e9c59e7c613413b13b3ca6870a`**; producción publicada
**`d0323c756eccc68482dd8b5674dc5c5843531aff`**, con corrección de tests posterior
`aed9eb5a`. El commit documental posterior conserva exactamente ese código.

| Métrica Sonar | Referencia recuperada `05caf8eb` | Este análisis |
|---|---:|---:|
| Cobertura general | 76,5 % | **76,6 %** |
| Cobertura nueva | 82,0 % | **82,2 %** |
| Líneas generales cubiertas / medibles | 42577 / 55319 | **42825 / 55588** |
| Condiciones generales cubiertas / medibles | 3559 / 4984 | **3666 / 5107** |
| Líneas nuevas cubiertas / medibles | 10859 / 12886 | **11138 / 13192** |
| Condiciones nuevas cubiertas / medibles | 2808 / 3775 | **2915 / 3898** |
| Líneas / condiciones nuevas sin cubrir | 2027 / 967 | **2054 / 983** |
| Duplicación nueva | 0,08442 % | **0,08159 %** |
| Incidencias nuevas | 0 | **0** |
| Quality Gate | OK | **OK** |

Condiciones exactas: cobertura nueva **≥80 %**, duplicación nueva **≤3 %**,
incidencias nuevas **=0**. Referencia **PREVIOUS_VERSION de
2026-11-21T16:46:16+0000**, sin nueva projectVersion. Configuración SHA
`84aec1246aae6a1a3949f786449faf9c19a10894cfcb044adcf81866f18f08a6`, perfiles,
reglas, exclusiones y umbrales conservados. `SONAR_LABEL` sólo nombra evidencias.
La instalación y el ajuste persistente `vm.max_map_count=524288` siguen vigentes;
no se reinicia el servidor, se modifican credenciales ni se toca Waveform Lab.

### Importación, alcance y objetivo 95

El scanner confirma lectura de `evidence/sonar/coverage.xml` y de
`frontend/advanced-reader/coverage/lcov.info`. Los hashes están en el JSON.
Python local mide **36405/50793 líneas (71,67 %)**; Python propio en Sonar mide
**36405/47928 (75,96 %)**. Las 2865 líneas restantes del XML están fuera del
alcance Sonar existente y ninguna está cubierta: su lista exacta queda en el
JSON. No se alteran exclusiones ni se atribuye el desfase a un fallo de importación.

Vitest mide **5382/6845 líneas (78,63 %)**; Chrome añade **322 líneas y 234
condiciones reales**, conservando denominadores de unidades. LCOV combinado:
**5704/6845 líneas (83,33 %), 3666/5107 condiciones (71,78 %)**. Se comprueban
hash de código ejecutado/publicado/mapeado, fuente y ubicación de ramas; no se
aceptan cohortes fallidas ni ramas inferidas del minificador. Sonar considera
además **802 números de línea presentes sólo en BRDA y 13 líneas de configuración**
fuera del LCOV. Se contrastó archivo por archivo: cero discrepancias entre las
líneas Sonar y la unión DA/BRDA en los archivos importados.

Nuevos contratos: structured_notes y structured_routes **100 %**, acciones de
aplicación **91,0 %**, helper nativo **94,6 %**, acciones React **85,7 %**, páginas
Cornell/CPI **96,0 %**. Se mantienen abiertas sus ramas negativas pendientes.
Un Gate OK no acredita 95 %. General: **46491/60695 observaciones**, faltan
**11170** adicionales a denominador fijo; nuevo **14053/17090**, faltan **2183**.
Hay 355/386 observaciones cubiertas más que antes, pero también crecen los
conjuntos medibles; la brecha absoluta del 95 % aumenta 18/22. No se oculta.

Déficit nuevo principal, líneas/condiciones: knowledge_graph.py **263/0**,
canvas.ts **65/74**, component.ts **58/76**, room.ts **54/53**,
concept_edit.py **101/0**, concepts.py **94/0**, StudyApp.tsx **41/50**.
Los diez archivos de tooling de la referencia conservan **82 observaciones
nuevas sin cubrir (2,70 % de 3037)**. No explican el déficit general ni sustituyen
los pendientes funcionales. El JSON lista los veinticinco mayores de ambos ámbitos.

### Commits locales y distinción de cambios

`2478bb7c` inventario inicial; `ec8ddca8` integridad de copia y CAS nativo;
`7d3ce7dd` HTTP/operaciones/filtros; `4af7c176` interacción React recuperable;
`e8203c25` recursos/filtros/última referencia; `25ea2d6f` formato del test;
`d0323c75` publicación de assets; `aed9eb5a` dobles/ruta portable corregidos;
`c1a29eb5` matriz verificada. El cierre documental se confirma aparte.

Entre 2803cc37 y aed9eb5a: código mantenido **777 líneas añadidas/97 sustituidas**
en 14 archivos; pruebas **1009 añadidas/3 sustituidas** en ocho archivos;
bundles **3422 añadidas/3421 sustituidas** en 28 rutas, incluyendo renombres
contados como baja/alta. Son deltas físicos de Git, no conteo de funciones ni
supresión de producto. La documentación del inventario se cuenta por separado.
La reducción del principal se conserva; no se minifica fuente mantenida, retira
validación, suprime pruebas o declara código trasladado como eliminado.
