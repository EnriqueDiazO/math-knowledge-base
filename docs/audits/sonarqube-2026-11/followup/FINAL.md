# Cierre de pendientes — 2026-11-21

**Quality Gate OK; cobertura nueva 96,1% (antes 31,2%).** Rama
`audit/sonarqube-2026-11`; commits previos preservados. Cambios sólo locales, sin
push ni merge; main permanece en 1bc8026f. Esta fase añade seis commits de trabajo
y el commit documental de cierre.

## Análisis confirmado y comparación

Análisis `f62b032f-c663-4c1c-97a2-c57a555387c0`, CE SUCCESS, fecha API
2026-11-21T19:41:12+0000. Revisión analizada:
`8723ab2ba555f414e9d840e5e4701254062cf89f`. HEAD del scanner coincide; el commit
posterior sólo contiene documentación/evidencia resumida. API y snapshot conservan
por separado revisión analizada y HEAD local.

| Control | Final anterior | Calibración sin nuevas pruebas | Cierre |
|---|---:|---:|---:|
| Python coverage.py | 28 810/44 278 = 65,07% | 29 024/44 302 = 65,51% | 29 246/44 350 = **65,94%** |
| Sonar cobertura general | 62,9% | 66,0% | **66,4%** |
| Sonar nuevas líneas cubiertas/total | 112/359 | 197/383 | **420/437** |
| Sonar condiciones nuevas cubiertas/total | 0/0 | 2/2 | **2/2** |
| Sonar cobertura nueva combinada | 31,2% | 51,7% | **96,1%** |
| Gate | ERROR | ERROR | **OK** |
| Bugs clásicos Sonar | 16 | 16 | **14** |
| Vulnerabilities / code smells | 3 / 61 | 3 / 61 | **3 / 61** |

El diagnóstico previo identifica el análisis anterior y sus 15 archivos en
DIAGNOSIS.md. La calibración fue análisis
`f65446d1-51c0-463b-b30c-67169958c771` sobre 392e8569. No se añadieron tests para esa calibración.

Referencia efectiva **idéntica**: PREVIOUS_VERSION heredado,
2026-11-21T16:46:16+0000. projectVersion sigue `not provided`; SONAR_LABEL sólo
nombra el JSON y no participa en el periodo. `reference.json` y check_reference
comprueban ese modo/fecha sin mutar la configuración del servidor.

Condiciones finales exactas:

| Métrica | Operador que falla | Umbral | Valor final | Estado |
|---|---|---:|---:|---|
| new_coverage | LT | 80 | 96,1 | OK |
| new_duplicated_lines_density | GT | 3 | 0,0 | OK |
| new_violations | GT | 0 | 0 | OK |

No se cambiaron el Gate, los perfiles/reglas activas, el periodo, las exclusiones,
las supresiones ni los omit. Se comprobó igualdad de claves de perfiles y cantidades
de reglas frente a baseline. La única propiedad nueva del scanner es la ruta LCOV;
el hash de configuración actual está en RESULTS.json. Las cifras generales tienen
el mismo alcance de fuentes, con más código y mejor medición; no un denominador
artificialmente congelado. El código nuevo creció de 359 a 437 líneas con los fixes
y guardas de esta fase. JS aporta además dos condiciones medidas desde LCOV.

## Causa demostrada del 31,2%

1. **Python se importaba correctamente**. El log anterior ya parseaba el XML
   corregido; no había rutas sin resolver. No se arregló un supuesto fallo de
   importación Python cambiando exclusiones.
2. **Faltaba instrumentación de procesos hijos/E2E**. pytest-cov 7 ya no inicia
   automáticamente coverage en hijos. Se añadió patch=subprocess y se ejecutó el
   runner E2E con coverage run, combinando sus datos. El primer smoke descubrió
   omit relativos mal resueltos si un hijo cambiaba cwd; se anclaron los mismos diez
   patrones a ROOT sin añadir exclusiones. Los 249 archivos del XML final son
   propios: cero tests, venv o .tools.
3. **Faltaba un reporte JS importable**. Los 107 tests ya pasaban, pero no generaban
   LCOV. Se fijó @vitest/coverage-v8 4.1.12 y la ruta al reporte; ahora Sonar registra
   Analysing [.../frontend/advanced-reader/coverage/lcov.info], sin errores de rutas.
4. **Faltaban pruebas de comportamiento del tooling**. Antes, sonar/quality/
   quality_mongo aportaban 284/359 líneas nuevas y 214/247 huecos (86,6% del déficit).
   No se habían comprobado los contratos de credenciales/HTTP, instalación, fallos
   del proceso, reporte obsoleto, comparación y liberación de recursos. Las nuevas
   pruebas reproducen fallos antes del fix y verifican sus efectos después.

La calibración, usando exclusivamente las pruebas existentes, añadió **85 hits de
líneas nuevas**: quality_mongo 56; export_knowledge_graph 19; QMD 6; rollback 1;
App/PdfJsController 3. Añadió también dos condiciones JS cubiertas. Las 24 líneas
nuevas de configuración del runner aún estaban sin medir: por eso 197/383 líneas y
2/2 condiciones equivalen a 199/385=51,7%, no a una comparación con denominador 359.
De los 85 hits recuperados, 56 (65,9%) corresponden al tooling de auditoría definido
arriba; los otros tienen función de aplicación. No se atribuye genéricamente toda
la mejora a «scripts» ni a nuevas pruebas.

El desglose final, con cada línea cubierta/no cubierta y condiciones por archivo,
está en NEW_COVERAGE.md y NEW_COVERAGE.csv. Quedan 17 líneas nuevas sin medir/cubrir,
13 en el tooling exacto; los motivos se explican individualmente. No impiden el
umbral conservado ni se eliminaron del denominador. Una línea puede ejecutarse
operacionalmente fuera del proceso medido y carecer además de una aserción
focalizada; estas causas no se suman como categorías mutuamente excluyentes.

## Cambios y verificaciones

REGRESSIONS.md relaciona cada commit con sus pruebas, los fallos antes del arreglo
y los resultados posteriores. Incluye las correcciones previas de rollback,
imágenes compartidas, parser/matemáticas, rutas/export y recursos del lector.
Esta fase corrige publicación de credenciales, vinculación a instancia, revisión
de snapshot, propiedad/limpieza de procesos, redacción de errores, decodificador
permitido de imágenes y helper PyVis roto. No modifica contratos Mongo ni requiere
replica set/transacciones. Se conservan los E2E de rollback exacto y última imagen
compartida sobre un standalone real.

Último comando integrado, sobre fuentes estables:

- **Python:** 1 832 aprobadas, 59 omitidas, 0 fallos y 0 errores; 128,65 s.
- **Mongo E2E:** 9 aprobadas, 0 fallos; 7,37 s, mongod/PID/dbpath/XDG propios y
  limpieza verificada. Son nueve de las omisiones opt-in del job anterior.
- **Resultado Python único:** 1 841 aprobadas y 50 pendientes por ZIP privado.
  No sumar las ejecuciones focalizadas repetidas como casos únicos adicionales.
- **Frontend:** 107 tests aprobados; LCOV líneas 1 266/1 508=83,95%, ramas
  736/1 063=69,24% redondeado (Vitest muestra 69,23%). TypeScript y
  ESLint pasan; npm audit completo cero en todas las categorías.
- **Entorno:** pip check y poetry check --lock pasan; avisos de deprecación de
  Poetry previos conservados. Sin cambios runtime Python adicionales en esta fase.
- **Ruff:** 2 157 avisos, mismas reglas/exclusiones (inicial 2 165; fase anterior
  2 156). Única diferencia de esta fase: I001 en un import de test nuevo, cosmético;
  no se hizo autofix masivo ni se ocultaron avisos. Agrupación histórica en RUFF.md.
- **Scanner:** código de salida 0, CE SUCCESS, XML y LCOV importados sin avisos de
  resolución; referencia comprobada antes y después. Las pruebas de build/Chrome
  previas se reutilizan: no cambia el bundle ni las versiones runtime; la opción
  JSON de grafos se conserva y sus 28 pruebas afectadas pasan.

Reportes generados/importados: coverage-unit.xml (29 188/44 350=65,81%),
coverage.xml combinado (29 246/44 350=65,94%), frontend/.../coverage/lcov.info.
Sólo el XML combinado y LCOV se importan. JUnit pytest.xml registra la suite Python;
no se configuró como reporte de tests Sonar. Copias finales, hashes, logs y datos de
API se preservan en evidence/sonar/followup-2026-11; RESULTS.json resume los datos
verificables versionados. El candidato previo se conserva identificado y no es la
fuente de estas cifras finales.

## Pendientes y límites

CLARIFICATIONS.md explica 65,8% preliminar frente a 64,12% de baseline, las 53
omisiones iniciales frente a 50 del ZIP, nombre/ruta/hash del archivo privado y la
comparación npm equivalente (21 a cero incluyendo dev/optional/peer).

SONAR_BUGS.csv clasifica las 16 claves originales. Se corrigen S5850 (redacción)
y S3923 (helper roto); quedan 14: siete asserts de tests que se relanzan tras cerrar
el cliente, cuatro invariantes de producción dentro de catch y tres órdenes ASCII
de manifiestos. Se documentan impacto/prioridad/solución/compatibilidad por clave;
no se cambian estados ni reglas para ocultarlos. No son 14 defectos funcionales
confirmados de severidad equivalente.

PYTHON_ADVISORIES.csv clasifica **64 avisos únicos / 76 entradas en siete paquetes**.
Pillow/dnspython/Tornado/SoupSieve tienen correcciones que exigen abandonar Python
3.10; pytest requiere major y cualificar plugins; pip/setuptools admiten 3.10 pero
requieren renovar y validar el entorno de construcción. Las mitigaciones de PNG/
WebP y basetemp privado son parciales: los paquetes siguen afectados, sin ignores.
El uso real instalado de Streamlit es Starlette/Uvicorn; Tornado requiere evaluar
Jupyter, no atribuir automáticamente sus avisos al servidor Streamlit.

Faltan las 50 comprobaciones del corpus autoritativo privado, la cualificación de
esas actualizaciones y los casos residuales de NEW_COVERAGE.md. El inventario
completo del resto de módulos y deuda continúa en INVENTORY.csv/FINDINGS.md; no se
sustituye por estos tres defectos iniciales ni por el Gate verde.

No se eliminaron módulos/paquetes en esta fase. Se retiró la rama duplicada del
helper y se reutilizó su JSON, con regresión. Las eliminaciones previas mantienen
su justificación en los informes históricos.

## Repetición

```bash
cd /home/enriquedo/PersonalProjects/math-knowledge-base
make sonar-scan SONAR_LABEL=followup-final
```

Usar otra etiqueta segura para conservar también la instantánea actual. La etiqueta
no modifica projectVersion. Se necesitan Docker/Sonar UP, mongod y las dependencias
npm/Python instaladas. La referencia fijada se comprueba; si cambió, el comando
aborta sin modificarla. No pasar sonar.projectVersion ni cambiar el periodo.

Persistencia del host ya comprobada: vm.max_map_count=524288 vivo y en
/etc/sysctl.d/90-mathmongo-sonar.conf. No hace falta otra intervención sudo ni se
sobrescribe su configuración. Procedimiento/reversión: docs/SONARQUBE.md.
