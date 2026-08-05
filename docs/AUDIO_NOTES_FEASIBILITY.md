# Factibilidad de notas de audio

## Dictamen

**AUDIO_FEASIBLE_WITH_MEDIA_ADAPTER**

MathMongo puede incorporar notas de voz breves para explicar una nota, una
Source o un documento Cornell/CPI, pero la base actual no las admite de forma
segura como si fueran imágenes. La capacidad de interfaz está disponible en
Streamlit 1.59.2; el trabajo pendiente es un adaptador de dominio, persistencia
portátil, límites y pruebas. No se implementa audio en esta release.

**Momento recomendado: después de clases.** La release docente debe conservar
el flujo actual de respaldo, restauración y PDF sin introducir un formato de
archivo ni datos personales nuevos.

## Evidencia en el entorno verificado

| Necesidad | Estado en Streamlit 1.59.2 | Consecuencia |
| --- | --- | --- |
| Grabar explicación | `st.audio_input(label, sample_rate=...)` | Devuelve un `UploadedFile` WAV; 16 kHz es el valor predeterminado y es adecuado para voz. |
| Subir un archivo | `st.file_uploader(...)` | Puede restringirse por extensión o MIME, pero la restricción del navegador es sólo orientativa. |
| Reproducir | `st.audio(data, format=...)` | Acepta bytes, archivos o datos de carga; el navegador sigue siendo parte del requisito de compatibilidad. |
| Descargar | `st.download_button(...)` ya está disponible en la interfaz | Puede entregar los bytes verificados sin exponer una ruta XDG. |

`st.audio_input` y `st.audio` fueron consultados con el ejecutable
`mathdbmongo/bin/python -m streamlit`; la versión instalada es **1.59.2**. La
API de grabación declara el MIME `audio/wav`. El límite de carga también queda
sujeto a `server.maxUploadSize`; no debe sustituir un límite específico de
audio del lado de la aplicación.

## Estado real de los medios

El soporte actual es deliberadamente visual:

| Área | Observación actual | Impedimento para audio |
| --- | --- | --- |
| Tipos permitidos | `ALLOWED_IMAGE_EXTENSIONS` sólo permite PNG, JPG/JPEG, SVG y PDF. | WAV, MP3 u OGG se rechazan antes de persistir. |
| Ruta | `save_media_asset` publica bajo `media/images`. | No existe un namespace de audio ni una política de publicación específica. |
| Asociaciones | Los registros usan `concept_ids`, `note_ids` e `image_ids`. | No hay contrato para Source, Cornell o CPI ni un campo que diferencie audio de imagen. |
| Vista y exportación LaTeX | Cornell, CPI y Cuaderno tratan esos IDs como imágenes y los preparan para `\includegraphics`. | Reutilizar `image_ids` rompería la semántica y los exportadores. |
| Integridad | El registro conserva `size_bytes`, SHA-256, MIME, fecha, descripción y tags. | Es una base útil, pero no valida contenedores de audio ni conserva duración, autoría o codec. |
| Límite | `MAX_IMAGE_UPLOAD_BYTES` tiene un valor predeterminado de 10 MiB. | El límite es de imagen; debe separarse de la política de audio. |

El exportador portable incluye el árbol de `media` y sus metadatos
`media_assets`; la restauración protege rutas y evita reemplazos inseguros. El
respaldo verificado de MathMongo cubre ese ZIP y su inventario de hashes. Eso
no vuelve portable una nota de audio por sí solo: una nueva colección o nuevos
campos de asociación deben estar incluidos expresamente en las colecciones
exportadas, validados al restaurar y comparados por el manifiesto.

Source Documents sólo almacena PDFs con blobs SHA-256 bajo un contrato
independiente; tampoco es un contenedor de audio.

## Frontera propuesta

| Pertenece a MathMongo | Permanece en Waveform Lab |
| --- | --- |
| Grabar o subir una explicación breve. | Recorte, segmentación y edición. |
| Reproducir y descargar el original verificado. | Forma de onda y limpieza. |
| Asociar el audio a una nota, Source, Cornell o CPI. | Etiquetado temporal detallado. |
| Mostrar duración, fecha, descripción y autoría declarada. | Transcripción por segmentos y análisis acústico. |
| Incluir bytes y metadatos en backup/restauración verificables. | Revisión profesional o procesamiento especializado. |

La primera entrega de MathMongo debería aceptar sólo **WAV grabado por
`st.audio_input`**, con una duración y tamaño reducidos y explícitos. La carga
de MP3/OGG puede evaluarse después de decidir un validador de contenedor y una
estrategia de obtención de duración; no debe añadirse sólo por la extensión del
archivo.

## Adaptador mínimo necesario después de clases

1. Definir un modelo de audio versionado, separado de `image_ids`, con
   `audio_id`, SHA-256, tamaño, MIME/codec permitidos, duración, fecha,
   descripción, autoría y un objetivo tipado (`note`, `source`, `cornell` o
   `cpi`).
2. Publicar bytes de forma atómica bajo un subárbol XDG dedicado, por ejemplo
   `media/audio`, aplicando permisos privados, rutas contenidas, nombres
   generados y limpieza limitada a archivos propios no confirmados.
3. Validar tamaño, MIME declarado, cabecera/contenedor y duración antes de
   publicar. Para WAV inicial, el módulo estándar puede validar el contenedor;
   otros codecs requieren una decisión explícita sobre dependencia y parser.
4. Mantener la asociación fuera de los helpers LaTeX de imagen y añadir
   índices/validaciones explícitos, sin mutar los documentos históricos de
   MathV0 durante el despliegue.
5. Extender exportación, importación y `mathmongo.backup` para inventariar el
   nuevo metadato y cada byte, comprobando SHA-256, conteos, asociaciones y
   blobs huérfanos tras restaurar a una base temporal nueva.
6. Añadir pruebas aisladas con WAV sintético, XDG temporal y base temporal:
   grabación/carga simulada, reproducción por bytes, descarga, rechazo de
   contenedor falso, rollback parcial y restore verificado.

## Riesgos que bloquean una incorporación apresurada

- La grabación requiere permiso de micrófono y una comprobación manual en los
  navegadores que se usarán en clase; la reproducción y el autoplay dependen
  también de políticas del navegador.
- El MIME o la extensión que ofrece una carga no son evidencia suficiente de
  que los bytes sean audio seguro.
- Duración, codec y datos de autoría son metadatos docentes y potencialmente
  personales; necesitan una política de retención y una interfaz de
  confirmación antes de guardar.
- No se debe reutilizar el flujo de imagen ni permitir que una pista de audio
  llegue a exportadores LaTeX o a los campos `image_ids`.

La decisión conserva una futura nota de audio sencilla dentro de MathMongo y
evita convertirlo en un editor de señal. Waveform Lab sigue siendo el destino
para cualquier operación sobre la forma de onda o análisis avanzado.
