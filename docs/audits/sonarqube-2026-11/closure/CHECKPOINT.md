# Checkpoint: auditoría cerrada antes de la esfera

**Los cinco criterios obligatorios se cumplen.** Código analizado: `3d6e0021`;
análisis `35032b37-475f-4c41-a9d5-6ca23bfb3506`, CE SUCCESS y Gate OK. El commit
que incorpora este checkpoint sólo añade documentación. Desde él se creará la
rama de funcionalidad; no se partió de main ni se implementó la esfera antes.

| Criterio | Evidencia de cierre |
|---|---|
| Defectos/avisos con resolución trazable | 14 bugs previos: 11 corregidos y 3 falsos positivos individuales; Sonar actual 0 bugs/0 vulnerabilities. Dependencias: los siete paquetes afectados siguen presentes y están corregidos en el perfil nuevo. SONAR_REVIEW.csv y PYTHON_ADVISORIES.csv conservan las decisiones. |
| Sin riesgos reales aceptados silenciosamente | Se resolvieron invariantes, privacidad/publicación PDF, colisiones QMD, identidad del plan, regex patológicos y errores del tooling. Quedan únicamente 32 avisos de estilo de API datetime.utcnow, soportada en el perfil <3.14 y conservando UTC naive; no implican un fallo actual. No se añadieron supresiones ni se aceptó un riesgo en nombre del usuario. |
| Verificación indispensable completa | ZIP original encontrado por la ruta indicada por el usuario; hash autoritativo confirmado y copia privada. Los 50 casos históricos antes omitidos pasan, además de las nuevas regresiones del corpus. Todos los 9 E2E opt-in se ejecutaron aparte en mongod propio. No queda ningún caso único obligatorio sin ejecutar. |
| Análisis comparable procesado | Gate OK: new_coverage 97.9 >=80, nueva duplicación 0 <=3, nuevas violaciones 0. PREVIOUS_VERSION / 2026-11-21T16:46:16+0000, reglas/umbrales/exclusiones conservados. XML y LCOV importados sin errores de resolución. |
| Informe, pruebas, commits y repetición | Este archivo, ENVIRONMENT.md, RESULTS.json, CSV de resoluciones/inventario/cobertura y registros locales identifican cada lote. El historial se conserva en la rama audit/sonarqube-2026-11. |

## Resultados y alcance

| Control | Último cierre previo | Cierre estricto |
|---|---:|---:|
| Sonar cobertura general | 66.4% | 67.5% |
| Python local | 29246/44350 = 65.94% | 29929/44454 = 67.33% |
| Sonar cobertura nueva | 96.1% | 97.9% |
| Líneas/condiciones nuevas cubiertas | 420/437 y 2/2 | 539/551 y 12/12 |
| Bugs / vulnerabilities Sonar | 14 / 3 | 0 / 0 |
| Code smells | 61 | 32 de estilo temporal/API, inventariados |
| Paquetes Python con avisos | 7 | 0 en el perfil cualificado |
| npm audit, todas las categorías | 0 | 0 |
| Ruff, misma versión/reglas | 2157 | 2156 |

El porcentaje nuevo final es (539+12)/(551+12)=97.87%, mostrado 97.9%.
Los 12 huecos nuevos restantes están en COVERAGE.csv; no se quitaron fuentes ni
se bajó el mínimo. Se preservan en followup/ las explicaciones de 65.8% preliminar,
64.12% baseline y del antiguo 31.2%: no eran el estado vigente al comenzar esta fase.

La medición V8 se amplió a los scripts propios al extraer un normalizador compartido.
LCOV pasa de 1266/1508 líneas y 736/1063 condiciones a 1281/1781 y 746/1233:
273 líneas y 170 condiciones adicionales en su alcance, con 15 y 10 cubiertas.
La interfaz conserva sus hits; el porcentaje V8 agregado baja por medir también
el tooling. Esos scripts ya estaban incluidos en Sonar. Esto explica parte de la
diferencia entre cobertura de líneas y cobertura combinada de Sonar; no representa
una regresión de pruebas ni una exclusión para mejorar resultados.

## Verificaciones por ejecución, sin sumar duplicados

- Suite integral del perfil nuevo: **1925 passed, 9 skipped, 0 failures/errors**,
  187.61 s. Los nueve omitidos son los E2E opt-in, ejecutados después: **9 passed**,
  7.89 s. El JUnit integral se conserva como complete-suite-pytest.xml.
- Tras sustituir sólo la extracción de título/referencia por un lector lineal:
  **46 passed**, todos los módulos que usan el parser. Se purgó únicamente el dato
  de cobertura de ese archivo modificado y se midió de nuevo con --cov-append;
  no se combinaron hits de sus números de línea antiguos con los nuevos.
- Contratos required-nullable añadidos después: **15 passed**. Son casos nuevos,
  no incluidos en los 1925 anteriores. Resultado Python único de esta fase:
  **1949 aprobados**, cero casos únicos obligatorios sin ejecutar.
- Comprobaciones focalizadas que se solapan con la integral: 75 compatibilidad;
  120 parsing/render/matemáticas; 63 recursos/invariantes/identidad; 4 invariantes
  bajo python -O; 54 rutas/exportaciones. No se vuelven a sumar como casos únicos.
- Frontend: **110 passed** (107 existentes +3 del normalizador); TypeScript,
  ESLint, build/publicación y audit npm pasan. Los 242 archivos publicados son
  byte a byte idénticos antes/después de sustituir los regex de normalización.
- Chrome real: runtime supervisor, PDF.js, worker/range, apertura desde Reading
  Space, asociación/anotaciones y round-trip pasan; cero page errors. Región PDF
  enfocada y desplazada por teclado. Borrador de formulario realmente sin enviar
  conservado al cambiar el tema. Los puertos/bases/XDG/dbpath se retiraron.
- pip check, poetry check --lock y construcción de wheel pasan. Wheel temporal de
  524 miembros con recursos del lector, sin ZIP privado, credenciales ni evidencia.
  Tcl 9.0.4 carga en el intérprete nuevo; no se afirma una prueba manual completa
  del lanzador gráfico nativo a partir de ese smoke.

La integral se ejecutó sobre d2ff0bbd; los cambios posteriores del lector lineal,
declaraciones de dependencias y normalización se comprobaron con sus controles
focalizados, actualizando cobertura y repitiendo sólo el scanner. RESULTS.json
identifica la revisión final analizada y los hashes de los reportes. No se atribuye
al scanner otro commit ni una ejecución integral que no ocurrió.

## Hallazgos nuevos y resolución

- El ZIP tiene los bytes aprobados, pero el plan v1 incluía nombre/mtime locales
  en su hash. Antes: 159 passed/8 failed/25 errors al ejecutar el corpus real.
  Se versionó la canonicalización como s1c1-v2, excluyendo sólo esos dos metadatos
  físicos del hash; el plan conserva su procedencia. Byte hash, inventario, base,
  candidatos, decisiones y autorización siguen vinculados. V1 se rechaza bajo la
  aprobación v2; no se migran manifiestos ni datos existentes automáticamente.
- Las cuatro invariantes de producción ahora generan errores explícitos también
  con -O. Los siete avisos en tests se resuelven simplificando catch/rethrow a
  finally, conservando aserciones y cierre del cliente.
- PDF se publica atómicamente con 0600. Un fallo conserva el PDF previo. Dos QMD
  con igual título y distinta identidad id/source conservan ambos archivos; se
  mantiene el nombre clásico cuando está libre y se usa sufijo estable ante
  colisión. Un archivo legado sin propiedad demostrable se conserva.
- Los patrones de diagnóstico, Markdown y HTML reproducían timeouts en datos
  temporales. Se conserva matemática y formatos válidos. Los normalizadores de
  licencias/SVG también eran cuadráticos; se sustituyeron por recorrido lineal.
  Los diagnósticos corregidos tardan aproximadamente 9 ms en el caso medido de
  500004 caracteres; no se extrapola ese dato a otras cargas/máquinas.
- Los fallos de las primeras AppTest con Streamlit nuevo se delimitaron: el padre
  real consume LAST_RESULT tras rerun, y el borrador sin enviar sólo existe en el
  navegador. Se corrigieron los harness para comprobar esos contratos y se añadió
  prueba real de Chrome; no se borraron las aserciones de guardado/idempotencia.

Las resoluciones falsas positivas son individuales y justificadas: orden ASCII
para inventarios, HTTP sólo loopback, campos required-nullable, colecciones de
bloqueos de aridad variable, región PDF realmente desplazable y avisos residuales
sobre regex corregidos. No se etiquetaron así los patrones que sí fallaban.

## Entorno, datos privados y repetición

Ver ENVIRONMENT.md. .venv es el perfil activo CPython 3.13.16; mathdbmongo queda
intacto como referencia 3.10. El ZIP original está en el respaldo XDG indicado por
el usuario. La copia del repositorio tiene 0600 y está ignorada; no se publica.

```bash
poetry install --with build
.venv/bin/python -m pip check
make sonar-scan SONAR_LABEL=closure-audit-repeat
```

Antes de acreditar otro cierre, debe existir el ZIP aprobado y deben comprobarse
los casos únicos, no sólo el Gate. SONAR_LABEL sólo nombra artefactos, no establece
projectVersion. Para guardar otra instantánea usar una etiqueta distinta; la
referencia efectiva se comprueba sin modificarla. No se usa análisis multirrama
ni capacidades de pago: las futuras comparaciones conservan este snapshot local
antes de analizar la rama de funcionalidad en el mismo proyecto Community.

La persistencia sysctl/servidor seguía correcta; no hubo reinstalación, nuevo sudo,
push, merge ni escritura en la base habitual. El inventario inicial se conserva;
INVENTORY_ADDENDUM.csv registra los 50 archivos de código/configuración/pruebas
revisados o modificados en esta continuación. El checkpoint autoriza comenzar la
esfera por la instrucción del usuario, sin otra confirmación rutinaria.
