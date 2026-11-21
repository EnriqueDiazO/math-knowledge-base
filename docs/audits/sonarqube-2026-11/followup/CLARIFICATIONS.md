# Cifras, alcances y pendientes verificables

## Cobertura preliminar y línea base cerrada

El apunte preliminar registró 43 083 sentencias y 14 755 sin cubrir: 28 328/43 083
= 65,75%, redondeado aproximadamente a 65,8%. Usaba selección de paquetes como
raíces; el XML tenía cinco rutas ambiguas. No era todavía una línea base importada
correctamente. Su configuración y XML completos no se conservaron como artefactos
inmutables; no se presentan como si fueran recuperables a partir del XML posterior.

La línea base cerrada es `baseline-coverage.xml`: 28 330/44 180 = 64,12%.
`.coveragerc` pasó a source=., relative_files=True e include_namespace_packages=True,
con los diez omit de entornos/dependencias/build documentados. Incluye todos los
módulos propios y los runners añadidos. La diferencia son 1 097 sentencias en el
alcance, dos cubiertas y 1 095 sin cubrir; no demuestra una regresión funcional.
Sonar importó este segundo XML sin errores de resolución. Su 62,0% tiene un
denominador diferente (analizadores Python/JS/TS y archivos sin reporte).

La fase anterior cerró con Python 28 810/44 278=65,07% y Sonar 62,9%. Esta fase
conserva los mismos source/omit, e instrumenta hijos y E2E. LCOV agrega medición JS,
incluidas ramas, al mismo conjunto de fuentes Sonar; por eso no debe atribuirse toda
la mejora global/nueva a pruebas añadidas. DIAGNOSIS y el cierre distinguen la
calibración sin nuevas pruebas de las regresiones añadidas después.

## Omisiones y corpus privado

JUnit inicial: 1 748 aprobadas, 53 omitidas, cero fallos/errores. Las 53 son 50
casos de ZIP ausente y tres E2E Mongo opt-in. Fase anterior: 1 783 aprobadas, 59
omitidas, cero fallos/errores; se añadieron seis E2E de regresión, también opt-in.
Los nueve E2E pasan en un job separado contra un mongod propio. Las 59 omisiones
en la suite general no equivalen a 59 casos nunca ejecutados: quedan 50 casos
únicos sin verificar por ausencia del archivo privado.

Archivo esperado, todavía ausente:
`/home/enriquedo/PersonalProjects/math-knowledge-base/mathkb_export_20260712_073927.zip`.
La constante autoritativa exige SHA256
`9b8660712171c7ab6db6fb3148deac23921330e1a640615ae6ae36c97e2165c8`.

| Módulo pytest | Casos pendientes |
|---|---:|
| test_source_catalog_migration_bootstrap | 20 |
| test_source_catalog_migration_production_gate | 14 |
| test_source_catalog_migration_apply_safety | 13 |
| test_source_catalog_migration_cli_apply | 1 |
| test_source_catalog_migration_planner | 1 |
| test_source_catalog_migration_zip | 1 |

Estos casos verifican lectura/hash/decisiones sobre el corpus histórico real,
plan de fuentes y referencias, bootstrap/reanudación/compensación y autorización
de aplicación con sus dobles de clientes. No se ejecutarán sobre MathV0. Los
fixtures sintéticos y E2E disponibles comprueban contratos generales; no reemplazan
la comprobación de ese corpus. No se ha creado un ZIP sustituto ni inventado éxitos.

## npm: 21 a cero con alcance equivalente

Ambos JSON se generaron con `npm audit --json` desde frontend/advanced-reader,
sin --omit, --production ni filtros de severidad. Incluyen producción, desarrollo,
optional y peer: baseline 8 high+13 moderate=21 paquetes; updated cero de todas las
severidades. El grafo cambia de 284 a 293 dependencias totales (prod 5 en ambos;
dev 268 a 277); el alcance de categorías es equivalente, no el número de nodos.
Vite/ESLint/Vitest forman parte de ambos alcances. Esta fase añade el proveedor
V8 compatible con Vitest y conserva otro audit completo, sin ignores.

## Problemas restantes, sin cambiar reglas

SONAR_BUGS.csv contiene las 16 claves originales, evidencia, impacto, prioridad,
solución, compatibilidad y estado. PYTHON_ADVISORIES.csv desduplica las 76 entradas
en **64 avisos distintos**: dnspython 2, Pillow 42, pip 7, pytest 1, setuptools 5,
soupsieve 3 y Tornado 4. Conserva alias, número de entradas originales y fixes por
aviso. No se suman alias como vulnerabilidades distintas ni se elimina el JSON bruto.

P1 significa atender una frontera de entrada con impacto directo o potencial;
P2 deuda/riesgo dependiente de configuración o actualización que requiere
cualificación; P3 código inactivo en este host o comportamiento correcto documentado.
No equivale a cambiar la severidad del servidor.

Corrección demostrada: redacción Pydantic y rechazo de TIFF disfrazado (fe093394).
Esto **no elimina los avisos del paquete Pillow**. PNG/WebP, metadata y usos
indirectos en dependencias aún requieren cualificar Pillow 13. La metadata oficial
de Pillow 13.0.0, dnspython 2.9.2 y Tornado 6.6.1 exige Python >=3.11; SoupSieve
3.0.2 y 4.0.0 exigen >=3.11.5. Los fixes mínimos dnspython 2.9.0 y
Tornado 6.6 también exigen >=3.11: no existe ahí una corrección parcial
compatible con 3.10 que se haya omitido. El proyecto soporta 3.10: no se fuerza una instalación
incompatible ni se afirma remediación completa. pytest 9.0.3 admite 3.10, pero cambia
major; los runners se mitigaron con --basetemp bajo directorios privados únicos.

pip 26.3 y setuptools 84.2.1 admiten 3.10. La restricción no es el intérprete: son
saltos mayores de herramientas antiguas del venv; requiere comprobar instalación
limpia/consumidores del build. El backend propio es Poetry, no setuptools. No se
modificaron arbitrariamente herramientas compartidas ni se dejaron de inventariar.

Streamlit 1.59 instalado implementa Server.start con UvicornServer (Starlette).
La atribución anterior de los avisos HTTP Tornado al servidor Streamlit fue demasiado
general. Tornado sigue instalado y usado por Jupyter; revisar allí el parseo HTTP y
las redirecciones antes de exponer ese servicio. No se demuestra explotación del
runtime local ni ausencia universal de riesgo.

Fuentes: metadata oficial de [Pillow](https://pypi.org/pypi/Pillow/13.0.0/json),
[dnspython](https://pypi.org/pypi/dnspython/2.9.2/json),
[Tornado](https://pypi.org/pypi/tornado/6.6.1/json),
[SoupSieve](https://pypi.org/pypi/soupsieve/3.0.2/json),
[pytest](https://pypi.org/pypi/pytest/9.0.3/json),
[pip](https://pypi.org/pypi/pip/26.3/json),
[setuptools](https://pypi.org/pypi/setuptools/84.2.1/json).
Los CSV enlazan cada advisory y evidence/sonar/followup-2026-11 conserva metadata
consultada. El inventario completo INVENTORY.csv, FINDINGS.md y la agrupación Ruff
previa siguen vigentes; estos pendientes no sustituyen la auditoría completa.
