# Fresh Database Lifecycle E2E

## Objetivo

Esta fase valida el recorrido de una instalación nueva sin depender de `MathV0`:
crear una Source administrada, crear y editar un Concept vinculado, exportar la
base, importarla en otra base físicamente inexistente y conservar
`id + source + source_id` durante todo el ciclo.

La corrida de aceptación no ejecutó migraciones, backfill ni escrituras sobre
bases reales. Tampoco modificó Sources o conceptos preexistentes.

## Aislamiento

La prueba `tests/test_fresh_database_lifecycle_e2e.py` requiere
`MATHMONGO_RUN_FRESH_DB_E2E=1`; sin esa variable queda `skipped`. Cada ejecución:

1. genera un sufijo de timestamp UTC más UUID aleatorio, salvo que el operador
   proporcione uno seguro para hacer visible la corrida;
2. deriva exactamente una base `mathmongo_e2e_fresh_<sufijo>` y una
   `mathmongo_e2e_import_<sufijo>`;
3. rechaza nombres protegidos, repetidos, demasiado largos o preexistentes;
4. imprime ambos nombres después de comprobar su ausencia y antes del primer write;
5. registra todos los comandos MongoDB mutantes y exige que sus destinos sean
   exactamente esas dos bases;
6. elimina sólo esos dos nombres en `finally`, incluso ante fallo;
7. usa un `TemporaryDirectory` para exports, backups y datos auxiliares, y exige
   que haya desaparecido al terminar.

La corrida final de aceptación utilizó exclusivamente:

- `mathmongo_e2e_fresh_20260719t014823_95abdfc80e81`;
- `mathmongo_e2e_import_20260719t014823_95abdfc80e81`.

Durante el desarrollo hubo reintentos con los sufijos `013637_3b2337ba2004`,
`013738_cf7246cc6424`, `013816_e91157e9c45c`, `014002_360e01ce8944`,
`014034_3f860a4b6c8d` y `014328_b7a5ec5a5994`, todos precedidos por
`20260719t`, además de la aceptación previa `014446_227dfd5fbbcf`. Cada
reintento autorizó sólo su pareja fresh/import, ejecutó el
mismo `finally` y quedó confirmado como ausente antes de continuar. Nunca se
reutilizó un nombre fijo.

Como control externo de sólo lectura se compararon los conteos de `MathV0`
antes y después: `sources=17`, `concepts=186`, `latex_documents=187`. La prueba
E2E no abre `MathV0`; el monitor de comandos confirmó que todos sus writes se
limitaron a la pareja temporal.

## Base inicialmente vacía

Sobre la base fresh se inicializaron los índices aprobados del Source Catalog
mediante `initialize_catalog_indexes` y sólo los índices core requeridos por
Concept/Edit mediante `ExistingDatabaseTarget.ensure_indexes`.

Después de crear los índices y antes de crear datos se comprobó:

- `sources=0`;
- `concepts=0`;
- `latex_documents=0`.

No se copió ninguna estructura desde `MathV0` ni desde otra base.

## Creación de Source

La Source se creó con el flujo real de Add Source:

```text
execute_add_source -> SourceCatalogService.create_source -> SourceRepository.insert
```

El resultado fue `persisted=True`, sin Reference opcional y con exactamente una
Source válida y activa. La Source se recargó desde MongoDB por su `source_id` y
se comprobó su nombre, estado e identidad estable.

## Creación de Concept

La Source activa apareció en las opciones de Add Concept mediante
`load_active_sources`. La selección se resolvió otra vez con
`resolve_active_source(source_id)` antes del guardado. El Concept se construyó
como `ConceptoBase`, se serializó con `build_concept_metadata` y se persistió
con `insert_concept_with_latex_atomic`, el mismo contrato usado por Add Concept.

No hubo texto libre ni creación implícita de Sources. Un `source_id` válido pero
inexistente devolvió `None`, no se reconstruyó por coincidencia de nombre y el
conteo de Sources permaneció en uno.

## Contrato source + source_id

Después del alta, los documentos mínimos fueron equivalentes a:

```json
{
  "concepts": {
    "id": "definition:fresh_lifecycle",
    "source": "Fresh lifecycle source",
    "source_id": "src_<uuid4>"
  },
  "latex_documents": {
    "id": "definition:fresh_lifecycle",
    "source": "Fresh lifecycle source",
    "source_id": "src_<uuid4>"
  }
}
```

Hubo exactamente un documento por `(id, source)` en cada colección y una sola
Source. `source` conserva el snapshot legible de `Source.name`; `source_id`
conserva el vínculo administrado estable.

## Edit Concept

La prueba invoca `update_concept_fields_preserving_identity` para cambiar título,
comentario y LaTeX. Tras el update:

- los `_id` MongoDB originales siguieron iguales;
- `id`, `source` y `source_id` siguieron iguales en ambos documentos;
- título/comentario y contenido LaTeX reflejaron el cambio;
- los conteos continuaron en uno y no hubo duplicados;
- ninguna Source fue consultada para inferir o reescribir identidad.

La primera ejecución real descubrió un defecto: PyMongo resuelve atributos
desconocidos de `MongoClient` como bases, por lo que
`getattr(client, "supports_transactions")` devolvía un objeto `Database` y su
conversión a `bool` fallaba. La corrección consulta sólo marcadores booleanos
declarados en la instancia o el tipo y después usa la topología real. Una
regresión reproduce la semántica dinámica de PyMongo y confirma el fallback
standalone sin perder identidad.

La auditoría de UI existente confirma con fakes/AST que Edit Concept muestra ID,
Source snapshot y `source_id` como sólo lectura y que el payload ordinario no
incluye campos identitarios.

## Exportación

`export_database_to_zip` generó un ZIP versionado dentro del directorio temporal.
La inspección del contenido JSON comprobó directamente, antes de importar:

- `concepts[0].source` y `concepts[0].source_id` presentes;
- `latex_documents[0].source` y `latex_documents[0].source_id` presentes;
- un documento en cada colección;
- una Source portable con el mismo ID.

No se perdió ningún campo. No fue necesario modificar exportación.

## Importación

La segunda base permaneció físicamente inexistente hasta llamar a
`import_zip_into_database(..., new_database=True)`. La importación restauró una
Source, un Concept y un documento LaTeX. Las consultas posteriores comprobaron
el mismo `source`, el mismo `source_id`, el título editado y el LaTeX editado,
sin duplicados ni Sources implícitas.

Después se ejecutó el contrato real de actualización de base sobre el destino
existente. Su dry-run retuvo `source_id` en las acciones de `concepts` y
`latex_documents`; el apply idéntico terminó con `inserted=0` y `replaced=0`, y
los documentos modernos conservaron el vínculo. No fueron convertidos en legacy.

La ejecución aislada de database update reveló además que la inicialización de
índices importaba prematuramente el parser de ingestión y su dependencia
`rapidfuzz`. `YamlLatexParser` pasó a importarse sólo dentro de `ingest_folder`,
sin cambiar ingestión ni índices. Así el inicializador core real queda utilizable
sin cargar componentes ajenos al flujo.

## Compatibilidad legacy

La compatibilidad se comprobó sin migrar ni reescribir documentos:

- `ConceptoBase` acepta Concepts sin `source_id`;
- `build_concept_metadata` omite un `source_id=None`;
- el insert atómico legacy no agrega un campo nulo;
- Edit Concept preserva la ausencia del campo en ambos documentos;
- los backups históricos con layout raíz y Concepts sin `source_id` siguen
  importándose;
- un mismatch de `source_id` se reporta como identidad stale y nunca se
  reconstruye por nombre;
- import sólo restaura las Sources declaradas en el archive y no sintetiza otras.

Los 43 tests enfocados de backup/import pasaron. No se ejecutó ninguna migración
legacy ni backfill.

## Limpieza

El `finally` eliminó exclusivamente las dos bases de cada corrida. La corrida
final verificó que ambos nombres ya no aparecían en `list_database_names` y que
el conjunto de destinos de write observado era exactamente la pareja autorizada.

El `TemporaryDirectory` eliminó ZIPs de export, backups pre-update y cualquier
directorio de datos temporal. No quedó archivo temporal del E2E.

## Pruebas

| Cobertura | Resultado |
|---|---:|
| E2E habilitado, corrida final | 1 passed |
| E2E sin variable | 1 skipped |
| Add Source: repository/service/workflow | 37 passed |
| Add Concept + source/source_id + Edit Concept | 47 passed |
| Regresión enfocada de Edit Concept | 26 passed |
| Backup/import | 43 passed |
| Database update | 26 passed |

Las pruebas de UX vacía verifican que cero Sources produce cero opciones,
`can_save=False`, botón deshabilitado y el mensaje “Crea primero una Source desde
Add Source”. Tras crear la primera Source, las pruebas verifican selección por
`source_id`, ausencia de texto libre y cero escrituras al catálogo desde Add
Concept.

## Validaciones

- E2E habilitado: PASS.
- E2E deshabilitado: SKIP esperado.
- suites enfocadas de Add Source/Add Concept/Edit/source link: PASS.
- suites enfocadas de import/export/database update: PASS.
- Ruff estricto en los archivos nuevos y el servicio de Edit: PASS.
- Ruff sobre `mathdatabase/mathmongo.py`: PASS con exclusión explícita de su
  deuda preexistente de docstrings, typing y whitespace fuera del cambio.
- compilación en memoria de los Python modificados: PASS.
- `git diff --check`: PASS.
- conteos de `MathV0` antes/después: 17/186/187, sin cambio.
- bases temporales y archivos temporales al cierre: ausentes.

## Hallazgos

1. El round-trip actual ya preservaba `source_id`; no hubo que tocar portabilidad.
2. El flujo real descubrió y corrigió una detección transaccional incompatible
   con el acceso dinámico de PyMongo.
3. La carga diferida del parser elimina un acoplamiento no requerido al
   inicializar índices o aplicar updates.
4. Add Concept depende de una Source administrada existente, no de `MathV0` ni
   de strings libres.
5. El esquema moderno y la compatibilidad legacy pueden coexistir sin migración.

Respuestas expresas:

- **¿El proyecto depende de MathV0?** No. El ciclo completo funcionó desde una
  base vacía y la prueba E2E no abrió `MathV0`.
- **¿Un usuario nuevo puede crear su propia estructura?** Sí. Puede crear la
  primera Source y después Concepts vinculados en su propia base.
- **¿Add Concept obliga a usar una Source existente?** Sí. Cero Sources bloquea
  el guardado y una selección desaparecida/inactiva se rechaza.
- **¿Los conceptos modernos sobreviven export/import?** Sí. `source` y
  `source_id` sobrevivieron export, import y database update.
- **¿Los backups legacy siguen siendo aceptados?** Sí. Los formatos históricos
  sin `source_id` siguen cubiertos y no se les aplica backfill.

## Limitaciones

- La UI completa no se automatizó en navegador; se usaron helpers reales más
  fakes y análisis AST para estados visuales no fiables.
- El MongoDB local de aceptación es standalone, por lo que el E2E ejercitó el
  fallback compensable. El camino transaccional sigue cubierto por tests unitarios.
- `mathdatabase/mathmongo.py` conserva deuda Ruff preexistente fuera de esta fase;
  no se amplió el alcance para reformatear un módulo legacy completo.
- Hubo reintentos de desarrollo con parejas temporales adicionales; todos
  respetaron aislamiento por ejecución y quedaron eliminados. La corrida final
  de aceptación usó exactamente las dos bases declaradas arriba.

## Próxima fase

La siguiente fase puede añadir esta prueba opt-in al procedimiento local/CI con
un MongoDB efímero y, por separado, planificar la limpieza incremental del módulo
legacy `mathdatabase/mathmongo.py`. No hace falta una migración de `MathV0` para
habilitar usuarios nuevos.
