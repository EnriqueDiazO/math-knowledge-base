# Source Link Contract

## Objetivo

Introducir un contrato dual para conceptos: conservar `source` como identidad
legacy obligatoria y permitir `source_id` como vínculo opcional hacia una fuente
gestionada.

## Contrato legacy

- `source` continúa siendo obligatorio.
- La identidad, la detección de duplicados y el rollback conservan el selector
  histórico `(id, source)`.
- Un concepto sin `source_id` sigue siendo válido y no serializa el campo con
  valor `null` en los documentos construidos con `exclude_none=True`.

## Contrato dual

- `source_id: str | None = None` forma parte de `ConceptoBase`.
- Cuando `source_id` existe, la inserción atómica lo persiste tanto en
  `concepts` como en `latex_documents`.
- Cuando no existe, ambos documentos mantienen su forma legacy.

## Invariantes conservadas

- `source` no se deriva ni se reemplaza por `source_id`.
- Los índices y consultas basados en `(id, source)` no cambian.
- El rollback de una inserción parcial continúa eliminando por `(id, source)`.
- No se crean registros en `sources` y no se modifica MongoDB durante esta
  fase.

## Archivos modificados

- `schemas/schemas.py`
- `editor/db/concept_repository.py`
- `tests/test_concept_source_link_contract.py`
- `docs/PHASE_SOURCE_LINK_CONTRACT.md`

## Pruebas añadidas

Las pruebas cubren conceptos legacy y vinculados, obligatoriedad de `source`,
serialización con omisión de `None`, persistencia simétrica en `concepts` y
`latex_documents`, y conservación de las consultas y del rollback legacy.

## Validaciones

- Prueba enfocada nueva: `7 passed`.
- Pruebas enfocadas y consumidores legacy relacionados: `48 passed`.
- Compilación en memoria de los tres Python modificados: correcta.
- `git diff --check`: correcto.
- Ruff mantiene los 77 hallazgos ya presentes en los dos módulos legacy; el
  archivo de pruebas nuevo no introduce hallazgos.
- Suite completa: `1329 passed, 51 skipped, 4 failed`. Los cuatro fallos son
  los mismos del baseline previo (`tests/test_xdg_media_paths.py` y
  `tests/test_xdg_mutable_guards.py`).

## Limitaciones

- No hay migración ni backfill de conceptos existentes.
- Add Concept todavía no consume el catálogo de fuentes gestionadas.
- Edit Concept todavía no administra el vínculo.
- Importación y exportación no se ampliaron explícitamente para gestionar el
  campo.
- El flujo legacy `MathMongo.ingest_folder` conserva su construcción separada
  de documentos LaTeX y no fue modificado.
- No hay cambios visuales ni escrituras reales a MongoDB.

## Próxima fase

Integrar en Add Concept la selección de una fuente gestionada y poblar el par
`source`/`source_id` sin romper la entrada legacy.
