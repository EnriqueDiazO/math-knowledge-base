# Guía de Database Import

`Database Import` ofrece dos operaciones distintas. Revise el modo seleccionado antes de cargar
el respaldo.

## Crear, actualizar y reemplazar

**Crear base nueva** importa en un nombre que todavía no existe. Nunca reutiliza ni sobrescribe
una base existente. `MathV0` sólo es válido si no existe con ese nombre exacto.

**Actualizar base existente** fusiona un respaldo con una base ya creada. Puede seleccionar
`MathV0`; no la borra, no la renombra y no la recrea. Las bases `admin`, `config` y `local` están
bloqueadas.

**Reemplazar o reflejar** no forma parte de Database Import. No existe una opción para borrar lo
que falte en el respaldo. Un reemplazo total requiere otro procedimiento y otro contrato de
confirmación.

## Flujo de actualización

1. Seleccione **Actualizar base existente**.
2. Elija la base de destino y una estrategia.
3. Cargue el ZIP y pulse **Analizar actualización**.
4. Revise el resumen por colección, blobs, medios, advertencias y errores bloqueantes.
5. Elija una política para cada conflicto, incluso cuando quiera conservar la versión actual.
6. Escriba exactamente el nombre de la base y pulse **Actualizar _nombre_**.

El análisis es un dry-run: valida y compara sin crear colecciones, documentos, índices ni
archivos. Si el ZIP o el destino cambian después del análisis, el sistema exige analizar otra vez.

## Estrategias y conflictos

**Fusión segura** es la opción predeterminada. Inserta documentos nuevos, omite los idénticos,
conserva datos locales y no sobrescribe conflictos.

**El respaldo prevalece** permite usar la versión del respaldo para un conflicto concreto. Cada
reemplazo requiere una selección explícita; los documentos locales ausentes del ZIP se conservan.

**Conservar versión actual** inserta elementos nuevos y mantiene la versión de la base en todos
los conflictos.

Un conflicto significa que la misma identidad estable existe con contenido canónico diferente.
La pantalla muestra cantidades y decisiones, pero no expone IDs completos ni JSON de los
documentos.

## Colecciones

El inventario se obtiene comparando `metadata.json` con los archivos JSON del ZIP. Los conteos,
codificaciones y nombres deben coincidir y ser seguros.

- Una colección nueva del respaldo se crea, incluso si está vacía.
- Una colección presente sólo en la base se conserva sin cambios.
- Una colección vacía en el respaldo nunca elimina documentos existentes.
- Una colección conocida usa las identidades y validadores de sus modelos e índices actuales.
- Una colección futura se marca como **no administrada**, exige Extended JSON declarado y usa
  `_id` como identidad. Sin `_id` seguro, la actualización queda bloqueada.

No se importan índices desde el ZIP. Tras la fusión se aplican únicamente los IndexManagers
conocidos; no se inventan índices para colecciones futuras.

## Backup, blobs y recuperación

Antes de la primera escritura se crea un respaldo completo con fecha y hora bajo el directorio
XDG de backups. El respaldo se vuelve a leer y sus conteos se comparan con la base. Si no puede
crearse o validarse, la actualización no comienza.

Los PDF y medios se validan por tamaño y SHA-256 cuando el formato lo declara. Un archivo ausente
se publica mediante staging temporal y operación atómica; uno idéntico se omite. El mismo destino
con bytes distintos bloquea el plan. Los archivos locales ausentes del respaldo no se eliminan.

Si ocurre un fallo después de iniciar escrituras, la UI informa cuántas operaciones terminaron,
conserva la ruta del respaldo validado y habilita una recuperación explícita tras confirmar el
nombre exacto. Un fallo parcial nunca se presenta como éxito.

## Limitaciones

- No hay modo mirror, borrado de ausentes ni reemplazo total.
- Una colección genérica sin `_id` no puede fusionarse automáticamente.
- Los conflictos siempre requieren una decisión manual.
- No se depende de transacciones MongoDB; la protección usa dry-run, backup, comprobaciones de
  concurrencia, validación posterior y un diario de operaciones para recuperación.
- Un respaldo inválido, corrupto, con path traversal, referencias rotas o índices administrados
  incompatibles se rechaza antes de actualizar.
