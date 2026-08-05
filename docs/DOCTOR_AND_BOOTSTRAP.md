# Doctor y bootstrap seguro

`python -m mathmongo.doctor doctor` inspecciona sin crear estructuras ni
mostrar contenido privado. Informa el producto, base activa, host saneado,
versiones Mongo/FCV/PyMongo, colecciones, conteos, validators, índices,
Source Catalog, Source Documents/PDF (incluidos blobs sin metadata), Reading
Space y rutas XDG. No abre ni muestra el contenido de documentos ni archivos.

```bash
MONGODB_DB=MathV0 python -m mathmongo.doctor doctor
```

El bootstrap es independiente, explícito y aditivo. Sin `--apply` (o con
`--dry-run`) sólo muestra cada operación planificada. Con `--apply` requiere
que `--confirm-database` coincida exactamente con el destino; rechaza siempre
`MathV0` durante la preparación docente y no borra ni sustituye documentos.

```bash
python -m mathmongo.doctor bootstrap \
  --database MathV0_teaching_bootstrap \
  --confirm-database MathV0_teaching_bootstrap

python -m mathmongo.doctor bootstrap \
  --database MathV0_teaching_bootstrap \
  --confirm-database MathV0_teaching_bootstrap \
  --apply
```

El plan crea únicamente las colecciones conocidas `sources`, `references`,
`source_documents` y `document_reading_state`, más índices aprobados por los
gestores existentes. Cualquier conflicto de índice bloquea la aplicación; no
hay `--drop` ni modificaciones de validators ajenos.
