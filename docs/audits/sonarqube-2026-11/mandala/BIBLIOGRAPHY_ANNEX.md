# Anexo activo: DOI/ISBN y captura Mathfield

Se incorpora la petición explícita del 21 de noviembre. Complementa habitación,
editor, inventario y Sonar; no los sustituye. No hay contratación, facturación,
subida de notas/PDF ni dependencia de IA para recuperar metadatos.

## Contratos inspeccionados

El catálogo existente separa Source, Reference y SourceDocument. Reference tiene
DOI normalizado, ISBN, autores, edición, idioma, BibTeX y procedencia; la importación
BibTeX y las decisiones de duplicados ya existen. El ISBN se valida sin alterar
los valores legados inválidos que el catálogo conserva para revisión. La nueva
entrada debe validar estrictamente la consulta antes de cualquier petición.

No existe todavía adaptador Crossref/DataCite/Open Library en el repositorio.
La propuesta en línea debe usar el guardado y las decisiones de duplicados del
catálogo, sin reemplazar manualmente registros ni asignar una nueva identidad a
una fuente por cada cita. Se mantiene separado el localizador de un pasaje.

Fuentes oficiales consultadas:

- [Crossref REST](https://www.crossref.org/documentation/retrieve-metadata/rest-api/)
  y [acceso](https://www.crossref.org/documentation/retrieve-metadata/rest-api/access-and-authentication/).
- [DataCite público](https://support.datacite.org/docs/rest-api) y
  [GET DOI](https://support.datacite.org/docs/api-get-doi): no autenticación para
  metadatos públicos findable; ausencia no demuestra inexistencia de un DOI.
- [Open Library, condiciones y límites](https://openlibrary.org/developers/api):
  consultas humanas de bajo volumen, caché, identificación configurable; límite
  conservador por defecto de una petición por segundo. No recolección masiva.
- [Obras, ediciones e ISBN](https://openlibrary.org/dev/docs/api/books):
  `/isbn/{ISBN}.json` admite ISBN-10/13 y resuelve una edición. No se incorpora
  `/api/books`, señalado como legacy.
- [Search API](https://openlibrary.org/dev/docs/api/search): título/autor devuelve
  candidatos de obra y edición; no confundir first_publish_year con publish_date
  de la edición consultada.
- [Caso editorial 10.1007/BF01106749](https://link.springer.com/article/10.1007/BF01106749):
  “Singular integral operators along a complex contour”, V. I. Nyaga, 1977. La
  verificación editorial no afirma disponibilidad libre del PDF ni identifica
  sus páginas con las de una versión original/traducción diferente.

## Implementación y evidencias del lote

- Crossref → DataCite para DOI; Open Library ISBN/edición y título/autor. La
  normalización de consulta valida ISBN y conserva el texto original. Se amplió
  la detección/repositorio de duplicados con equivalencias válidas ISBN-10/978-13;
  979 no se convierte a ISBN-10. No se reescriben los fingerprints históricos.
- Transporte HTTPS de endpoints definidos, redirecciones al mismo proveedor,
  JSON limitado a 1 MiB, conexión/lectura de hasta 5 s, presupuesto de consulta
  de 20 s, una repetición como máximo, cache de 64 respuestas durante una hora,
  serialización por proveedor y espera conservadora de una petición por segundo.
  Una lectura ya en curso puede consumir su timeout antes de devolver el estado.
  429 conserva Retry-After y no bloquea la interfaz durmiendo períodos largos.
  MATHMONGO_METADATA_CONTACT configura contacto explícito en el User-Agent;
  no se extrae de documentos ni se exige una cuenta para la versión gratuita.
- Add Source y Add Reference en Edit Source ofrecen DOI / ISBN junto a Manual
  y BibTeX. Propuesta editable con detalles plegados; tipo, título, autores/roles,
  fecha, contenedor, páginas de publicación, edición, idioma e identificadores.
  Los resultados de obra no heredan el año de primera publicación a una edición.
- En el mismo editor visual, «Buscar o añadir referencia» abre el selector sin
  salir del documento. El estado vive en el borrador local, incluidos consulta,
  selección, correcciones y request_id; una respuesta A no sustituye a la B.
  «Guardar ficha y citar» usa SourceCatalogService: coincidencias explícitas,
  Reference ID estable y asociación a la Source elegida. Reutilizar no modifica
  metadatos existentes, citekey ni otras asociaciones. Un ID de propuesta estable
  permite reconciliar el reintento tras una respuesta perdida.
- Actualizar desde Edit Source muestra diferencias y aplica sólo campos elegidos.
  Conserva clave y raw BibTeX, manuales no seleccionados y Source IDs. Compara
  revisión bibliográfica y todo el BSON durante la escritura: detecta incluso
  cambios con el mismo milisegundo y escritores ajenos sin actualizar timestamp.
- CitationLocator separa página impresa, índice PDF, capítulo, sección, teorema y
  pasaje. La ficha mantiene páginas de publicación distintas. La nota canónica
  admite ese localizador sin PDF obligatorio; publicar es una segunda acción.
  El concepto conserva Reference ID/localizador y una proyección compatible con
  el formato bibliográfico legado. Sus tres exportadores LaTeX añaden los datos
  disponibles sin cambiar numeración previa. Metadatos externos se tratan como
  texto, con escape TeX y URL delimitada; no se ejecutan como instrucciones.
- Antes de borrar físicamente una Reference se inspeccionan Source, conceptos,
  SourceDocument, notas, anotaciones y evidencia, también archivados. Se impide
  borrar una referencia usada después de desasociar su Source.

No se ha contratado ni activado Google Books. No se encontró una vía RIS previa
que debiera reemplazarse. Se preservan captura manual y el parser/importación
BibTeX canónicos, sin convertir ausencias de catálogo en una prohibición de alta.

### Verificaciones

30 pruebas offline de proveedores/transporte/identificadores; 12 casos de captura,
BSON, CAS, referencias usadas, nota sin PDF y exportación sobre mongod propio;
una prueba AppTest con widgets reales y fallo posterior que conserva correcciones;
177 pruebas Vitest, TypeScript, ESLint y build local. Los tests de proveedores
contienen respuestas fijas: no dependen de Internet ni sustituyen el ZIP privado.

El recorrido real, con esos proveedores de prueba en un wrapper temporal que no
existe en producción, pasa en Chrome y Firefox: no resultado, caída de proveedor,
DOI, propuesta corregida, duplicado, reutilización de ID/clave y localizadores,
vuelta al mismo documento, guardado y relectura desde Mongo propio. El cuerpo
legado representativo se abre y guarda por el editor real y conserva sus 12368
caracteres. Las capturas/evidencias de contenido privado permanecen ignoradas en
`evidence/sonar/mandala-2026-11/bibliography/{chrome,firefox}`.

Las consultas **reales**, independientes de esos fixtures, se hicieron el
22-11-2026 a las 00:24 UTC (21 de noviembre local). Crossref recuperó el artículo
de Nyaga, inglés, 1977, 21(3), 228–231; Open Library recuperó ISBN
9780140328721 / 0140328726, Fantastic Mr. Fox, edición Puffin de 1988.
[Resumen público acotado](BIBLIOGRAPHY_LIVE_RESULTS.json) contiene proveedor,
fecha, clase de registro y hash del JSON normalizado; el cuerpo completo de las
respuestas se conserva como evidencia local. No acredita cobertura de todo DOI
ni libro, ni disponibilidad del PDF.

### Pendientes que siguen activos

La habitación debe abrir y recuperar también notas existentes con este mismo
editor (el adaptador y la persistencia ya están probados; la entrada de habitación
sigue pendiente). Falta el recorrido completo fuente → anotación → nota → dos
vistas, la comprobación de selección exacta/scroll en navegación de habitación,
y compilar/inspeccionar visualmente un PDF representativo con la nueva cita.
La selección implementada respeta la referencia principal del modelo actual;
no crea una biblioteca paralela ni exige claves o comandos manuales.

El inventario conserva por separado todos los archivos aún pendientes. La
comparación Sonar está en [BATCH3_RESULTS.json](BATCH3_RESULTS.json): CE SUCCESS,
Gate OK, 85,5 % nueva y 70,6 % general sobre bbf8eba4. No se cambiaron perfiles,
período, exclusiones ni umbrales para aprobarlo. El inventario y los pendientes
manuales siguen abiertos.

## Referencia visual Mathfield

Se consultaron [teclado](https://mathlive.io/mathfield/virtual-keyboard/) y
[personalización pública](https://mathlive.io/mathfield/guides/customizing/).
La referencia aporta campo de fórmula, selector numérico/símbolos/alfabeto/griego,
edición, variantes y controles de teclado. Se conserva el azul profundo; no se
adopta el fondo blanco de la ilustración. Las partes públicas `content`,
`container`, `virtual-keyboard-toggle` y `menu-toggle` permiten adaptar su aspecto
sin tocar el DOM interno del componente. El teclado real ya pasa el recorrido
de guardado y recuperación tanto en Chrome como en Firefox; se comprobaron clics en las cuatro distribuciones, entrada virtual, deshacer y
rehacer, variante por pulsación mantenida y ausencia de escritura al cancelar.
El teclado alfabético tiene una fila adicional: se corrigieron altura de host y
teclas después de reproducir selectores tapados. No se manipula el DOM privado
ni se parchea MathLive; se usa su contenedor/eventos y partes CSS públicos.
