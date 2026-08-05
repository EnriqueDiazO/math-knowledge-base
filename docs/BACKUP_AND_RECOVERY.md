# Backup y recuperación docente

MathMongo es el producto; `MathV0` puede ser la base histórica activa. Un
backup no renombra, fusiona ni reemplaza esa base.

## Flujo obligatorio

1. Selecciona explícitamente la base con `MONGODB_DB` y confirma la identidad
   sin conectarte:

   ```bash
   mathmongo config
   ```

2. Crea un backup verificable. El comando usa el exportador portátil existente
   y genera un ZIP más un manifiesto externo con SHA-256, inventario de
   archivos, conteos, índices, validators, versiones, FCV cuando está
   disponible y el HEAD de Git.

   ```bash
   python -m mathmongo.backup backup --output-dir /ruta/segura/backups
   python -m mathmongo.backup verify-backup /ruta/segura/backups/archivo.manifest.json
   ```

3. Restaura primero en una base nueva y distinta. El comando rechaza `MathV0`,
   la base de origen, bases del sistema y cualquier destino que ya exista.

   ```bash
   python -m mathmongo.backup restore-to-new-database \
     /ruta/segura/backups/archivo.manifest.json \
     --target-database MathV0_teaching_restore
   ```

4. Ejecuta `doctor-backup`, abre la aplicación configurada contra la copia y
   revisa documentos, media, PDFs, índices, validators y asociaciones antes de
   cambiar `MONGODB_DB`.

   ```bash
   python -m mathmongo.backup doctor-backup /ruta/segura/backups/archivo.manifest.json
   ```

## Garantías y límites

- El backup no escribe en la base de origen; sí crea exclusivamente sus
  archivos bajo el directorio de salida indicado.
- El ZIP conserva media XDG y blobs PDF mediante el exportador portátil. El
  manifiesto comprueba el hash del ZIP y el hash/tamaño de cada miembro.
- La restauración aplica índices y validators del manifiesto sólo después de
  importar a una base destino previamente ausente.
- Ningún comando muestra credenciales: la URI del manifiesto y los errores se
  sanea antes de mostrarse.
- No uses `dropDatabase`, `--drop` ni acciones de borrado total como parte del
  flujo docente. Conserva backup, manifiesto, versión de Git y el árbol XDG
  correspondiente para poder volver atrás.
