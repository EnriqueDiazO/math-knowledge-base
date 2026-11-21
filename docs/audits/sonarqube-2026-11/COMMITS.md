# Commits locales y reversión selectiva

Todos están en `audit/sonarqube-2026-11`, a partir de `main@1bc8026f`. No se hizo
push, merge a main ni cambios de etiquetas. Se conservó el árbol de trabajo original
(limpio); no hubo modificaciones del usuario que separar de estos commits.

| Commit | Lote |
|---|---|
| 8c60d64e | Infraestructura Sonar/PostgreSQL, scanner, cobertura y guía inicial |
| 87ed3bed | Rollback exacto y conservación de imágenes compartidas; regresiones reales |
| bea2fe74 | Referencias Markdown cortas, mapping YAML y rutas QMD |
| f8be5bfa | Restricción de miniaturas en el mismo callback de metadata |
| 68165817 | Pins de seguridad compatibles, lock correcto y bundle lector reconstruido |
| 92449bdf | Ramas/imports/locales redundantes demostrados |
| 3f0daf49 | Reparar make export/grafo con base explícita y salida segura |
| 4d496c87 | Persistencia host, instalador scanner, evidencia nueva y E2E aislados |
| 8f18a79a | HTML/JSON de grafos seguros, listas de tipo/títulos opcionales y fallback |
| 4b8cb48c | Truncado opcional del zip de referencias explícito, sin cambio de comportamiento |

El commit posterior de entrega contiene sólo informes/inventarios de auditoría; su
hash se obtiene con `git log -1 --oneline` y se comunica en la respuesta final.
La revisión de código analizada por Sonar es 4b8cb48c, no ese commit documental.

## Revisión y reversión de un lote

Desde un árbol revisado y limpio, crear una rama para el revert:

```bash
git status --short
git switch -c revert/mathmongo-audit-review
git show --stat 8f18a79a
git revert 8f18a79a
```

Ese ejemplo revierte sólo el lote de grafos; reintroduce sus defectos anteriores.
Elegir el hash del lote que se desea retirar. Los commits posteriores pueden depender
del retirado y producir conflictos: resolverlos por contenido, sin reset/clean ni
restauraciones que descarten trabajo. Repetir las pruebas pertinentes después.
`git revert --abort` cancela únicamente un revert en curso si se decide conservar
los cambios existentes. Para retirar varios lotes relacionados, hacerlo en orden
inverso a su aplicación y revisar cada diff.

Para revertir dependencias/bundle, retirar el commit 68165817 en esa rama y sincronizar
sus entornos con los manifiestos resultantes, por ejemplo:

```bash
mathdbmongo/bin/python -m pip install -r requirements-dev.txt
cd frontend/advanced-reader
npm ci
npm run build
```

El build usa las fuentes de la rama elegida y puede producir un bundle distinto si
se conservan otros commits de UI. Revisarlo y probarlo. No se desinstalan herramientas
ni se borran datos/volúmenes como efecto de un revert Git.

## Detener o retirar sólo la infraestructura

Con la rama que contiene el Compose y sus archivos privados:

```bash
make sonar-down
```

Conserva los cuatro volúmenes y todos los resultados. `make sonar-up` los reutiliza.
No usar `down -v` ni prune. Si se revierte la infraestructura, detener estos servicios
antes de retirar sus archivos y revisar los commits posteriores que dependen de ella.
No detener Docker si lo usan otros proyectos. El ajuste de host y su reversión exacta
están en `docs/SONARQUBE.md`; Git no modifica `/etc/sysctl.d/`.

## Commits de la fase de pendientes

| Commit | Responsabilidad |
|---|---|
| d797505b | Diagnóstico antes de nuevas pruebas; análisis/periodo/desglose inicial |
| 392e8569 | Instrumentación hijos/E2E, LCOV V8, alcance de cobertura conservado |
| 45300f68 | Credenciales atómicas/vinculadas, revisión del servidor, limpieza y PID Mongo |
| fe093394 | Redacción de entradas Pydantic y decodificadores permitidos de branding |
| 0c455575 | Tests instalador/orquestación/CLI y referencia de comparación comprobada |
| 8723ab2b | Helper PyVis roto, JSON existente compartido y regresión de opciones |

El commit documental posterior añade el cierre, CSV de los 16 bugs, los 64 avisos
Python únicos, cobertura por archivo y guía de repetición. La revisión analizada es
8723ab2b; ese commit documental no cambia fuentes, pruebas ni configuración.
Las regresiones y evidencia de cada lote están en followup/REGRESSIONS.md.

## Cierre estricto previo a la esfera

La continuación desde `41c25714`, sus quince commits de código/infraestructura y
sus regresiones se detallan en [closure/COMMITS.md](closure/COMMITS.md).
El checkpoint vigente está en [closure/CHECKPOINT.md](closure/CHECKPOINT.md);
los apartados anteriores conservan las revisiones y resultados históricos.
