# Construcción de GUIA_READING_SPACE_MATHMONGO

Este documento registra el procedimiento canónico y el artefacto PDF generado para la guía de Reading Space de MathMongo 0.13.0.

## Artefactos canónicos

- Fuente: `docs/user-guide/GUIA_READING_SPACE_MATHMONGO.md`
- PDF: `docs/user-guide/GUIA_READING_SPACE_MATHMONGO.pdf`
- Assets: `docs/user-guide/images/reading-space-v013/`
- Plan de capturas: `docs/user-guide/images/SCREENSHOT_PLAN.md`
- Generador: `scripts/build_reading_space_guide.sh`

El generador sólo acepta la fuente y el destino anteriores. Los HTML, CSS, perfiles de Chrome y PDF intermedios se crean bajo `/tmp` y se eliminan mediante traps.

## Comando canónico

Desde la raíz del repositorio:

```bash
scripts/build_reading_space_guide.sh
```

No se necesita red, no se descarga contenido y no se modifica MongoDB. El script valida primero la fuente, las herramientas, los 12 assets y los tres enlaces locales.

## Dependencias verificadas

| Dependencia | Versión usada | Función |
|---|---:|---|
| Python | 3.10.12 | Validación de enlaces y reescritura limitada del HTML temporal. |
| Pandoc | 2.9.2.1 | Conversión Markdown → HTML autocontenido. |
| Google Chrome | 149.0.7827.102 | Impresión headless HTML → PDF. |
| Poppler `pdfinfo` | 22.02.0 | Inspección del PDF. |
| Poppler `pdffonts` | 22.02.0 | Verificación de fuentes incrustadas. |
| Poppler `pdftotext` | 22.02.0 | Verificación de texto seleccionable. |
| Poppler `pdftoppm` | 22.02.0 | Render visual de todas las páginas. |

Chrome se ejecuta sin acceso de resolución externa y con un perfil temporal. Los enlaces publicados no se visitan durante la construcción.

## Metadatos del build final

- Fecha: 2026-07-19
- Zona horaria de la fase: America/Mexico_City
- Versión documentada: 0.13.0
- Commit de la fuente y del generador: `207c7c8b4f05aa449608dd3040fc3c5ef32646c9`
- Formato de página: A4, 594.96 × 841.92 puntos
- Páginas: 21
- Tamaño: 1,647,527 bytes
- SHA-256: `9f8cc7515d941ff8512dbb07c82252665a58b3b02fa6d07252043212e7ce1f36`
- PDF: versión 1.4, tagged
- Creator: HeadlessChrome 149
- Fuentes: Noto Sans, Noto Sans Bold, Noto Sans Mono, Liberation Sans Bold y glifos Type 3; todas incrustadas

Comparación con el PDF anterior:

| Métrica | Anterior | Final |
|---|---:|---:|
| Páginas | 62 | 21 |
| Tamaño | 6,848,375 bytes | 1,647,527 bytes |
| SHA-256 | `fa9346a7481962c1b9fc241f4d83386c321f813f37b70f1c453f8f80492b7e83` | `9f8cc7515d941ff8512dbb07c82252665a58b3b02fa6d07252043212e7ce1f36` |

La reducción se debe a la sustitución de la narrativa visual anterior por 12 capturas actuales y a una maquetación más compacta; no es una eliminación de secciones obligatorias.

## Assets incluidos

Todos son PNG RGB de 1600 × 1000:

1. `01_active_database.png`
2. `02_add_source.png`
3. `03_source_details.png`
4. `04_add_concept.png`
5. `05_reading_space.png`
6. `06_advanced_reader.png`
7. `07_evidence_link.png`
8. `08_cuaderno.png`
9. `09_cuaderno_promote.png`
10. `10_edit_concept.png`
11. `11_legacy_link.png`
12. `12_document_builder_or_graph.png`

## Enlaces

El Markdown conserva enlaces relativos a los tres documentos relacionados y el script comprueba que existan. Para que el PDF no retenga rutas efímeras de `/tmp`, sólo el HTML temporal reescribe esos tres `href` hacia el tag inmutable `v0.13.0-managed-source-workflow` del repositorio publicado.

El PDF final contiene exactamente tres anotaciones URL:

- `MANAGED_SOURCE_WORKFLOW.md`
- `RELEASE_NOTES_v0.13.0_MANAGED_SOURCE_WORKFLOW.md`
- `VERSION_CLOSURE_MANAGED_SOURCE_WORKFLOW.md`

## Validación ejecutada

| Comprobación | Resultado |
|---|---|
| `bash -n scripts/build_reading_space_guide.sh` | Sin errores. |
| Validador integrado | 12 imágenes locales y 15 enlaces locales válidos. |
| Pandoc | HTML autocontenido generado sin warnings. |
| Chrome headless | PDF generado y publicado por reemplazo atómico en el mismo filesystem. |
| `pdfinfo` | 21 páginas A4, PDF 1.4, tagged. |
| `pdffonts` | Todas las fuentes con `emb=yes`. |
| `pdftotext` | 605 líneas, 3,919 palabras y 26,011 bytes de texto extraído. |
| `pdfinfo -url` | Tres enlaces HTTPS al tag estable; ninguna ruta `/tmp`. |
| `pdftoppm -png -r 120` | 21 PNG RGB de 992 × 1404, uno por página. |
| Revisión visual | Páginas 1–21 inspeccionadas; sin clipping, desbordes o imágenes ilegibles. |

`qpdf` no estaba disponible y no forma parte de las dependencias requeridas. Las verificaciones de Poppler, apertura, extracción de texto, fuentes, enlaces y render completo pasaron.

## Seguridad de publicación

El PDF anterior se conserva sin cambios hasta que Pandoc y Chrome concluyen correctamente. Antes de publicar, el script verifica que el PDF temporal sea no vacío, que comience con `%PDF-` y que `/tmp` comparta filesystem con el directorio destino. Sólo entonces usa un rename que reemplaza el archivo final de forma atómica.

Si alguna validación falla, el script termina con código distinto de cero, conserva el PDF anterior y elimina sus temporales.

## Solución de problemas

### Falta un asset o enlace local

El script enumera el objetivo roto y termina antes de ejecutar Pandoc. Corrige la ruta en el Markdown o restaura el archivo; no omitas el validador.

### Pandoc no encuentra las imágenes

No ejecutes Pandoc manualmente sin `--resource-path`. Usa el comando canónico, que fija el directorio de recursos al directorio de la guía.

### Chrome o Pandoc no están disponibles

Instala o habilita la dependencia mediante la administración normal del entorno y vuelve a ejecutar el script. El generador no descarga herramientas.

### `/tmp` está en otro filesystem

El script falla de forma segura para no reemplazar parcialmente el PDF. Ajusta el entorno para que la publicación atómica sea posible; no cambies el script a una copia directa insegura.

### El checksum cambia tras regenerar

Chrome puede registrar metadatos de creación distintos entre ejecuciones. Publica y registra el checksum del artefacto concreto que haya pasado la validación completa.
