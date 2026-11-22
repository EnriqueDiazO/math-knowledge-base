# Comparación de línea base y revisión final

> Registro de la fase anterior. El cierre vigente y sus cifras están en
> [followup/FINAL.md](followup/FINAL.md). Se conserva este informe como evidencia histórica.

Revisión inicial de aplicación: `1bc8026f`; configuración añadida antes de baseline, posteriormente commit `8c60d64e`. Revisión final analizada y confirmada por la API: `4b8cb48c5c0b21cf09c2f7f02f7fc7b8f248e391`. Los commits posteriores de entrega sólo documentan resultados.

CE inicial: SUCCESS, analysisId `9fd1bdae-7827-4b7c-839e-7791f9f4c72d`. CE final: SUCCESS, analysisId `f7d5bcc2-691b-4a6e-ae2b-91d8f759911e`.

Hash de propiedades idéntico: `841f93701f9fc485ed6b051961753156368173feaf438c5b27b4551e6642ac78`. Perfiles/lenguajes y recuento de reglas activas idénticos. Sin ampliación de exclusiones ni cambios de Gate.

| Métrica | Inicial | Final |
|---|---:|---:|
| Bugs (clasificación clásica) | 17 | 16 |
| Vulnerabilities (clasificación clásica) | 3 | 3 |
| Code smells (clasificación clásica) | 61 | 61 |
| Cobertura Sonar (%) | 62.0 | 62.9 |
| Cobertura de líneas Sonar (%) | 62.0 | 62.9 |
| Líneas a cubrir, Sonar | 45706 | 45803 |
| Líneas sin cubrir, Sonar | 17376 | 16993 |
| Duplicación (%) | 1.9 | 1.9 |
| Bloques duplicados | 86 | 86 |
| Complejidad ciclomática agregada | 16050 | 16073 |
| Complejidad cognitiva agregada | 17756 | 17788 |
| Security hotspots | 0 | 0 |
| Deuda estimada (minutos) | 480 | 480 |
| ncloc (incluye configuración admitida) | 89799 | 89907 |
| Archivos fuente con métricas | 279 | 281 |

La complejidad agregada aumenta por los runners y guardas nuevas; no se pretendió reducirla mediante una reescritura. Los defectos de datos/HTML confirmados por regresiones no estaban, en su mayoría, detectados por las reglas automáticas. Las métricas son evidencia complementaria, no una medida exhaustiva de seguridad.

## Quality Gate

**Inicial: OK. Final: ERROR**, procesamiento final completado. Falla únicamente `new_coverage=31.2%` frente al mínimo 80%. Duplicación nueva 0% y nuevas violaciones 0 satisfacen sus condiciones. Se conserva el código de salida no cero del scanner.

El Gate inicial no mostraba una condición de cobertura nueva porque aún no tenía un periodo comparable con líneas nuevas. El Gate y sus umbrales son los mismos; no debe interpretarse el OK inicial como aprobación de toda la deuda histórica.

Cobertura de líneas nuevas: 112 cubiertas / 359 a cubrir (247 sin cubrir). Entre las áreas con mayor déficit instrumental: scripts/sonar.py 34.8% (131 líneas nuevas sin cubrir), quality_mongo.py 0% (63), export_knowledge_graph.py 31% (20) y quality.py 0% (20). Los runners se ejecutaron operacionalmente fuera del proceso medido por pytest-cov; ese hecho no se presentó como cobertura instrumentada. El frontend tiene tests/Vitest y navegador aprobados, pero no se generó LCOV.

Próximo lote recomendado: pruebas de contrato HTTP/lifecycle y fallos de arranque/credenciales del tooling; instrumentar E2E y frontend en un job separado, definiendo una nueva comparación explícita si cambia el alcance de cobertura. No ocultar estos módulos ni bajar el 80%.

## Cobertura y pruebas locales

| Control | Inicial | Final |
|---|---:|---:|
| pytest unitario/integración disponible | 1748 passed, 53 skipped | 1783 passed, 59 skipped |
| Fallos / errores pytest | 0 / 0 | 0 / 0 |
| Cobertura Python local | 28330 / 44180 = 64.12% | 28810 / 44278 = 65.07% |
| Ruff, mismas reglas | 2165 | 2156 |
| Frontend Vitest | 107 passed | 107 passed |
| TypeScript / ESLint | pasan | pasan |
| npm audit: paquetes afectados | 21 | 0 |
| pip-audit: entradas / paquetes | 146 / 15 | 76 / 7 |
| Poetry lock | inconsistente | verificado |

Las 53 omisiones iniciales son 50 casos con ZIP privado ausente y 3 E2E opt-in. Las 59 finales añaden 6 nuevos E2E opt-in. Los **9 E2E Mongo únicos pasan aparte** sobre un standalone temporal; sólo los 50 casos del ZIP permanecen sin ejecutar. No se inventó ni sustituyó ese corpus autoritativo.

La última aclaración sintáctica del parser (`zip(..., strict=False)`, equivalente al valor predeterminado) recibió además 15 regresiones focalizadas aprobadas antes del último scanner. La cobertura mantiene las mismas líneas y el mismo alcance. El scanner final se repitió sobre HEAD estable para confirmar la revisión exacta.

El XML corregido contiene todos los módulos Python propios con rutas de repositorio, sin errores de resolución al importarlo. Sonar calcula líneas ejecutables con su analizador e incluye frontend sin LCOV; su porcentaje no es el de coverage.py. La diferencia 65.07% frente a 62.9% no es un fallo de importación.

## Clasificación MQR disponible

| Calidad / severidad | Inicial | Final |
|---|---|---|
| reliability_issues | {"INFO":0,"LOW":0,"MEDIUM":15,"HIGH":63,"BLOCKER":0,"total":78} | {"INFO":0,"LOW":0,"MEDIUM":14,"HIGH":63,"BLOCKER":0,"total":77} |
| security_issues | {"INFO":0,"LOW":2,"MEDIUM":1,"HIGH":0,"BLOCKER":0,"total":3} | {"INFO":0,"LOW":2,"MEDIUM":1,"HIGH":0,"BLOCKER":0,"total":3} |
| maintainability_issues | {"INFO":0,"LOW":1,"MEDIUM":32,"HIGH":17,"BLOCKER":0,"total":50} | {"INFO":0,"LOW":1,"MEDIUM":32,"HIGH":17,"BLOCKER":0,"total":50} |

Estas categorías pueden solaparse; no sumar MQR y categorías clásicas como si fuesen problemas distintos. La API conserva también issues cerrados; SONAR_ISSUES.csv recoge su estado, mientras esta tabla usa las métricas vigentes del servidor.

## Evidencia conservada

`evidence/sonar/` (local, ignorado): XML/JUnit, logs baseline/final, JSON de métricas/issues/hotspots/perfiles, avisos de dependencias, resultados E2E y prueba de reinicio persistente. `analysis-summary.json` conserva en Git la comparación esencial sin secretos. El servidor fue detenido/iniciado con los targets documentados y mantuvo el mismo análisis y credenciales.
