# S2: Documents PDF y web asociados a Sources

## Alcance

S2 incorpora Documents persistentes a la página **Edit / Analyze Source**. Un
Document pertenece a una Source, puede asociarse opcionalmente a una Reference
de esa misma Source y puede ser un PDF subido o un recurso web HTTP(S). S2 no
crea anotaciones, notas de lectura, evidencia de conceptos ni relaciones nuevas
con `concepts`.

## Modelo y persistencia

La colección `source_documents` almacena exclusivamente metadata validada. Los
identificadores de dominio son `doc_<uuid4>` y cada PDF inicial contiene una
versión `dver_<uuid4>` con número 1, SHA-256, tamaño, MIME, nombre original y
ruta lógica. MongoDB nunca recibe bytes ni rutas absolutas.

Los PDFs se publican por contenido bajo:

```text
${XDG_DATA_HOME:-~/.local/share}/mathmongo/
  source_documents/blobs/sha256/ab/<sha256>.pdf
```

Los directorios controlados son privados (0700) y las hojas son 0600. La ruta se
deriva únicamente del hash; se rechazan symlinks, archivos no regulares, tamaño
inválido, cabecera distinta de `%PDF-`, cambios durante lectura y contenido que
no corresponda al SHA esperado. La publicación es atómica y nunca reemplaza ni
borra blobs. El mismo hash puede ser reutilizado por Documents de bases o Sources
distintas.

## Reglas del servicio

El servicio revalida que la Source exista y que una Reference opcional esté
asociada a ella. La identidad de duplicado es `(source_id, sha256)` para PDF y
`(source_id, url_normalized)` para web. Un reenvío equivalente devuelve
`identical`; metadata distinta para la misma identidad devuelve `conflict`. Si
un blob nuevo quedó publicado y MongoDB falla después, el resultado es
`partial`: el blob content-addressed se conserva intencionalmente.

Las URL sólo aceptan `http` y `https`, requieren host, rechazan credenciales y
no provocan solicitudes de red desde el backend. La metadata editable queda
limitada a Reference, título, descripción, idioma, tags y derechos. Los IDs,
Source, kind, contenido, versiones y fecha de creación permanecen inmutables.

Los índices de `source_documents` están aislados del plan histórico de 15
índices del Source Catalog. Se aplican como parte de una escritura S2 confirmada;
abrir o inspeccionar la página no crea colección, índices ni directorios.

## UI y visor

La sección **Documents** contiene lista, alta PDF y alta web. El alta PDF sigue
upload → validación/metadata → confirmación → persistencia. La lista permite
editar metadata, inspeccionar integridad y archivar o reactivar. Un PDF se relee
desde el blob controlado y sus mismos bytes se entregan a `st.pdf`, a altura 800,
y al botón de descarga. El preview está aislado por base, Source, Document,
versión y SHA. No se usa `file://`, `webbrowser`, `Path.as_uri`, HTML ni PDF.js
propio.

## Backup portable

El export añade opcionalmente:

```text
collections/source_documents.json
source_documents/blobs/sha256/ab/<sha256>.pdf
```

`metadata.json` declara el inventario exacto de blobs con tamaño y SHA. Sólo se
exportan blobs referenciados por la base seleccionada; los huérfanos no se
escanean. El import valida primero colección, IDs, asociaciones, inventario,
paths, tamaños, cabeceras, hashes y conflictos. Después publica blobs sin
overwrite e inserta metadata preservando `_id`, IDs de dominio, versiones y
timestamps. Una segunda importación es un no-op para metadata y blobs idénticos;
cualquier diferencia bloquea antes de modificar la base.

La extensión portable es separada de `SOURCE_CATALOG_COLLECTIONS`; el
bootstrap, manifiesto y lector de migración legacy no cambian.
