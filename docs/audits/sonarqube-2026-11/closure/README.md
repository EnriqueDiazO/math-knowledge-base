# Continuación: cierre estricto antes de la esfera

Inicio 2026-11-21: rama audit/sonarqube-2026-11, HEAD
41c2571459c803e4ed42803c305f8865c3da88c1, árbol limpio y sin avances posteriores.
No se encontraron AGENTS.md aplicables. Skill developing-with-streamlit aplicada;
se conservan las restricciones de alcance y el gestor Poetry.

## Estado recuperado

Servidor UP 26.11.0.134175. Último análisis confirmado vía API:
f62b032f-c663-4c1c-97a2-c57a555387c0 sobre 8723ab2b. Diferencia hasta HEAD: sólo
documentación. Hashes de seis artefactos finales coinciden con RESULTS.json.
Por ello se reutilizan sus pruebas/coberturas como evidencia histórica aún válida
para ese código/entorno, sin presentarlas como nuevas ejecuciones.
Gate OK: coverage nueva 96.1 >=80, duplicación 0 <=3, nuevas violaciones 0.
PREVIOUS_VERSION heredado, fecha efectiva 2026-11-21T16:46:16+0000;
projectVersion not provided. SONAR_LABEL sólo nombra evidencia. No se cambia nada
de la referencia/umbrales/reglas/exclusiones. Sysctl vivo/persistente 524288;
no se solicita ni ejecuta otro ajuste de host.

## Orden y condición de parada

1. Resolver invariantes de producción y completar pruebas de errores/recursos.
2. Validar entorno paralelo y actualizaciones de seguridad por grupos pequeños.
3. Cerrar individualmente Sonar/Ruff/avisos aplicables y actualizar inventarios.
4. Ejecutar corpus autoritativo y análisis comparable para checkpoint estricto.
5. Sólo con todos los criterios cumplidos, rama de funcionalidad desde el checkpoint
   e implementación de esfera editable. No se inició código visual.

## Recurso externo pendiente

No se encontró mathkb_export_20260712_073927.zip tras buscar por nombre en
PersonalProjects, Descargas, Documents/Documentos, Escritorio/Desktop, attachments,
mathkb_backups, mongo_migration_backup, backups/respaldos/Respaldos, MathV0,
math_knowledge_graphs, Proyectos/ProyectoGit, phd, Shared y el montaje propio
/media/enriquedo. Sólo se enumeraron nombres; no se extrajeron archivos ni se
leyeron documentos personales. Log adicional: evidence/sonar/closure-2026-11/
corpus-search.json. Se solicitó su ruta local mientras continúa el trabajo independiente.

Las 50 pruebas de corpus siguen siendo requisito del checkpoint: validan hash,
contenido y decisiones históricos; los fixtures mínimos no son sustitutos. La
esfera permanece pendiente mientras falte ese recurso o cualquier otro criterio.

## Recurso recuperado y defecto descubierto

El usuario indicó el respaldo XDG en ~/.local/share/mathmongo/backups. Hash de bytes
verificado: coincide con AUTHORITATIVE_ZIP_SHA256; se creó copia 0600 en la ruta
esperada, ahora ignorada explícitamente por Git. Nunca se escribe en el original.
El primer intento de preparación se detuvo porque el ZIP no estaba ignorado; el
job siguiente aún dio 142 passed/50 skipped y no valida el corpus. Después de
preparar la copia, el primer job real dio 159 passed/8 failed/25 errors: el hash
semántico del plan dependía del nombre/mtime local del mismo ZIP.

Regresión de copia/renombrado/touch: 1 fallo y 1 control antes. Se excluyen sólo
filename/modified_at del payload semántico, conservándolos como procedencia en el
plan y preservando hash de bytes, inventario, base y decisiones. PLANNER_VERSION
pasa de s1c1-v1 a s1c1-v2. El hash autoritativo del plan se regenera desde el mismo
corpus y se fija en código; no se acepta un hash arbitrario ni se desactiva ningún
control. Los planes/decisiones/manifiestos v1 no se adoptan automáticamente: deben
volver a planificarse/revisarse, y no se migra ninguna base del usuario.

El hash anterior del plan era e91599d50c58bb88014911590d34c9f0fc46b1c989dec8f3f25fed007a33b44f;
el v2 es d4e6442a2c9e7d4502320fb4648204eb7c7de56debbd981e5b2711bcbe6f0bdd.
Con el arreglo, los seis módulos de corpus más dos regresiones aprueban **194 tests,
sin omisiones/fallos/errores**. Se añadió después una regresión de rechazo v1;
el lote de invariantes/identidad suma 7 aprobadas. Evidencia local privada en
historical-corpus-after.log, plan-identity-before.log y guards-identity-final.log.

La búsqueda inicial omitió el directorio XDG efectivo de respaldos; se corrige
el registro con la ruta indicada, sin mantener el recurso como bloqueo ausente.
