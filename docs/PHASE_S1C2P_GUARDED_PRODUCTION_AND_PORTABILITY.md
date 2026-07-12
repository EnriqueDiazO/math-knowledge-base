# Fase S1C2P — puerta MathV0 y portabilidad del catálogo

## Alcance del checkpoint de código

Este checkpoint añade una vía de producción separada al motor S1C2A y hace
portable el catálogo `sources`, `references` y
`source_catalog_migration_manifest`. No ejecuta la operación real, no crea
entidades en MongoDB y no amplía la frontera de escritura a ninguna colección
legacy.

La autorización aislada existente conserva sus dos prefijos y
`--allow-isolated-write`. La vía de producción acepta exclusivamente el nombre
exacto `MathV0` y exige simultáneamente:

- `--allow-production-write` sin combinarlo con la autorización aislada;
- confirmación exacta de base y frase de producción;
- los SHA-256 completos del ZIP autoritativo y del plan semántico;
- decisiones humanas completas y válidas;
- un export pre-apply privado, su SHA-256 repetido y un timestamp de freeze con
  zona horaria;
- doble captura estable del legacy, sin drift ni escrituras de preflight;
- ausencia física inicial de `sources`, `references` y del manifiesto.

No existen flags `force`, `skip`, `ignore`, `overwrite`, `drop` o rollback
destructivo.

El apply de MathV0 emite únicamente por stdout capturable; `--output` se rechaza
antes de leer el backup para que un destino de reporte inválido no pueda convertir
una aplicación ya completada en un error ambiguo. Si falla una comprobación o la
emisión posterior al motor, la CLI ordena consultar `apply-status` antes de reintentar.

## Backup como precondición

El backup no se acepta por la mera presencia de una ruta. El validador exige un
archivo regular 0600 dentro de un directorio 0700, ambos propiedad del operador,
sin componentes symlink, fuera del checkout instalado y de cualquier árbol
`site-packages`/`dist-packages`. Comprueba el SHA-256 de todos los bytes, la
identidad del inode antes/después y la estabilidad del directorio.

El archivo se abre con un único descriptor `O_NOFOLLOW`: exactamente los mismos
bytes alimentan SHA-256 y el parser ZIP, con `fstat` antes/después y comprobación
final de inode, propietario, tamaño, mtime y ctime. La metadata debe declarar
`database_name=MathV0`, formato
`mathkb_legacy_export` versión 1 y los diez conteos legacy autoritativos. El ZIP
no puede contener ninguna colección del catálogo. Además, el fingerprint
canónico de las diez colecciones debe coincidir con el snapshot autoritativo; no
basta un ZIP con las mismas cardinalidades. También deben coincidir el inventario
físico exacto de 15 archivos media y el SHA-256 canónico de sus nombres, tamaños
y bytes; un export sin media no es un respaldo completo. El inicio del snapshot debe
ser posterior al freeze; su finalización y mtime deben preceder la validación.
La ventana máxima entre finalización y el primer apply es de 24 horas. Esta
ventana convierte “fresco” en una condición verificable. El manifiesto conserva
basename, SHA-256, tamaño, timestamps, formato, permisos, conteos, fingerprints
legacy y media, y cantidad de archivos media,
pero nunca la ruta absoluta. Una reanudación posterior puede usar únicamente
ese mismo backup ligado al manifiesto aunque haya envejecido; no puede sustituirlo
por otro.

La CLI valida estructura, identidad y autoridad del backup antes de leer
configuración o construir el cliente. El motor vuelve a leerlo al entrar y otra
vez junto a la primera posible mutación; el primer apply comprueba allí también
la ventana fresca, mientras una reanudación exige coincidencia con la evidencia
durable. Después de esa segunda lectura vuelve a enumerar físicamente el catálogo
justo antes de crear el manifiesto: una colección vacía aparecida durante la
revalidación también bloquea.
La evidencia en memoria no contiene la ruta en su payload público y no se
persiste una ruta absoluta en el manifiesto.

El fingerprint live conserva además la identidad de tipos BSON, por lo que un
`ObjectId` y su representación string no son intercambiables. Se leen documentos
completos, sin excluir campos sentinel, y se incluyen todas las opciones devueltas
por `listIndexes` para el legacy. Antes de marcar el manifiesto `applied`, el motor
repite reconciliación de entidades, plan de índices y dos capturas legacy después
del último checkpoint observable.

## Formato portable

Las diez colecciones históricas mantienen el JSON legacy. Las tres colecciones
opcionales del catálogo se exportan sólo si existen y usan MongoDB Extended JSON
v2 canónico, declarado por colección en metadata. Así se distinguen sin
heurísticas `ObjectId`, strings hexadecimales y fechas BSON a milisegundos.

El exportador incluye únicamente las colecciones legacy aprobadas y las tres
opcionales presentes; no incorpora colecciones MongoDB desconocidas. La lista
legacy usada por “Clear All Data” no contiene el manifiesto ni las entidades del
catálogo. Serializa en memoria, construye el ZIP en un archivo anónimo
`O_TMPFILE` y lo publica con hardlink exclusivo: nunca reemplaza un nombre
existente. Antes de devolver éxito vuelve a comprobar inode, metadata y SHA-256
de los bytes publicados.

La importación procesa en orden `sources`, `references`, manifiesto. Conserva
`_id`, `source_id`, `reference_id`, `migration_id`, `source_ids`, timestamps,
mapas candidate-key → UUID, hashes y estado. Antes de escribir compara cada ID:
un documento idéntico se omite y uno diferente bloquea sin overwrite. También
rechaza References que apunten a Sources ausentes, colecciones fuera de la lista
aprobada y discrepancias entre metadata y los members físicos. Los exports
históricos no versionados sin inventario media explícito siguen admitidos; todo
export versionado exige formato/versión soportados y un inventario exacto en
nombres y tamaños. El codec declarado debe coincidir con el payload validado de
Source, Reference y manifiesto; fechas relajadas bajo una declaración canónica
se rechazan. Un ZIP histórico sin
catálogo sigue siendo válido y no materializa colecciones opcionales vacías.

Tanto la inspección como la importación aplican límites de members, tamaño total,
ratio de compresión, CRC, tipos regulares, paths normalizados y colisiones
archivo/ancestro. El lector del ZIP autoritativo mantiene abierto el mismo inode
que fue hasheado durante todo el parseo; un intercambio de pathname no puede
combinar la identidad de un archivo con el contenido de otro.

Una segunda importación del mismo ZIP omite tanto el catálogo como los
documentos legacy idénticos; los archivos media con los mismos bytes tampoco se
reescriben. Si la ruta original colisiona, el destino remapeado es estable por
contenido y se reutiliza también cuando procede de la convención histórica con
timestamp. Todos los documentos legacy ya remapeados se comparan antes de crear
media o colecciones: un conflicto bloquea sin efectos parciales. La creación de
media usa staging anónimo, publicación exclusiva y no sigue symlinks; una carrera
sólo adopta un archivo regular si su inode y sus bytes siguen siendo idénticos en
la comprobación final. La UI usa nombres temporales aleatorios, creación
`O_EXCL|O_NOFOLLOW`, elimina el upload al terminar y rechaza nombres protegidos
antes de construir `MathMongo`.

## Restauración

Con el mismo nombre exacto `MathV0`, un export versionado debe declarar también
`database_name=MathV0`. El destino puede estar vacío o contener sólo un subconjunto
idéntico del mismo ZIP, de modo que una restauración interrumpida sea reanudable y
una segunda importación sea no-op; cualquier colección o documento extra bloquea.
Un export histórico no versionado sólo puede entrar en un `MathV0` físicamente
vacío. El catálogo y el manifiesto conservan su identidad original. Los índices
MongoDB no forman parte del ZIP: después de una restauración debe revisarse
`Catalog Status` y aplicar explícitamente el plan exacto de 15 índices, sin
opciones semánticas adicionales, antes de considerar restaurado el rendimiento
operacional.

Con otro nombre de base, Sources y References son utilizables y conservan todos
sus IDs. El manifiesto se mantiene sin reescribir `target_database` ni
`manifest_key`: es evidencia histórica de MathV0 y el motor no puede reanudarla
contra el nombre alternativo.

La versión mínima es MathMongo 0.1.0 que incluya el checkpoint S1C2P. Las
compilaciones 0.1.0 anteriores a este checkpoint no entienden el codec del
manifiesto ni la puerta de producción y no deben usarse para este restore.

## Validación automatizada

Todas las pruebas de este checkpoint usan archivos temporales y bases fake. No
conectan a MongoDB real. Cubren la puerta de producción, backup y revalidación,
drift, presencia física del catálogo, regresión aislada, Extended JSON,
conflictos, asociaciones, timestamps, manifiesto y segunda importación no-op.

La aplicación real sobre MathV0 pertenece exclusivamente al checkpoint
operativo posterior al commit de este código.
