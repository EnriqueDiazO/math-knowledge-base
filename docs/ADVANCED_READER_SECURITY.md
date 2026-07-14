# Seguridad del Advanced Reader — S5A

## Principio de seguridad

El lector avanzado es un servicio local de un solo usuario, no un servicio
remoto. Escuchar en loopback reduce exposición, pero no sustituye autenticación
ni elimina ataques desde un navegador, extensiones, procesos locales o DNS
rebinding. S5A aplica defensa en profundidad y mantiene pequeño el límite HTTP.

El frontend se trata como cliente no confiable. `document_id`, página, headers,
query y payload JSON se validan en la API aunque hayan sido generados por la UI
oficial.

## Activos protegidos

- credenciales y URI MongoDB;
- metadata de Sources, References y Documents fuera de la proyección aprobada;
- paths XDG y HOME;
- blobs PDF content-addressed y sus bytes;
- estado de lectura real;
- texto consultado y seleccionado en el navegador;
- conceptos, anotaciones, notas y evidencia existentes;
- integridad del paquete instalado y de los assets frontend.

S5A no amplía el modelo de autorización: trabaja con el scope local existente.
Por ello no se ofrece escucha remota, multiusuario, colaboración o exposición en
LAN.

## Límites de confianza

```text
PDF no confiable
      │
      ▼
PDF.js endurecido en navegador
      │ selección/query efímeras
      X  no cruzan el límite HTTP

Navegador no confiable
      │ document_id / pdf_page / Range
      ▼
API loopback y schemas estrictos
      │ servicios explícitos
      ▼
MongoDB + XDG controlados
```

La API nunca acepta una ruta de archivo, URL de PDF, nombre de colección,
Source ID, Reference ID o Mongo URI enviados por el frontend. Esos valores se
resuelven desde el Document autoritativo.

## Binding, Host y same-origin

El launcher sólo admite `127.0.0.1`, `localhost` y `::1`. Rechaza `0.0.0.0`,
interfaces LAN, nombres arbitrarios y cualquier opción equivalente a
`--allow-remote`. No abre el navegador automáticamente.

Además del bind:

- se valida el header `Host` contra identidades loopback; el socket ya está
  ligado al único puerto configurado;
- se rechazan hosts con userinfo, caracteres ambiguos o dominios no aprobados;
- frontend y API se sirven desde el mismo origen en producción;
- no se instala middleware CORS global ni `allow_origins=["*"]`;
- no se aceptan credenciales cross-origin;
- el PUT de página exige JSON y contexto same-origin; `Origin` o Fetch Metadata
  incompatibles se rechazan;
- la configuración pública de Streamlit sólo acepta HTTP loopback sin query,
  fragmento ni credenciales.

Estas reglas reducen CSRF contra localhost y DNS rebinding. No convierten S5A en
un servicio seguro para exposición remota.

En desarrollo, Vite usa un proxy explícito a una API loopback conocida. Esa
apertura no se copia al build de producción y no se usa un proxy genérico
controlado por query.

## Acceso a Documents

Cada endpoint valida el `document_id` con el contrato S2 antes de consultar. La
API comprueba:

1. existencia del Document;
2. estado activo;
3. asociación a una Source existente;
4. asociación opcional a una Reference de la misma Source;
5. `kind=pdf` y payload PDF coherente;
6. versión actual válida;
7. integridad del blob.

Un Document archivado no se sirve. Un Document web devuelve
`document_not_pdf`: no se sigue su URL, no hay scraping, redirects, DNS ni
requests salientes.

Page Map es metadata auxiliar, no un requisito para abrir el PDF. La UI instala
primero la etiqueta `PDF page N`; si la consulta de Page Map no encuentra un
mapa o falla, conserva esa etiqueta y permite seguir leyendo. El fallo no se
transforma en una Book page inventada ni dispara una escritura de reparación.

La respuesta de metadata es una proyección explícita. Se excluyen
`logical_path`, paths absolutos, HOME, URI, credenciales, `_id`, documento Mongo
crudo y campos no necesarios. IDs internos sólo se muestran en detalles
técnicos cerrados.

## Resolución y apertura del blob

El cliente nunca selecciona el archivo. La API toma el SHA-256 validado de la
versión actual y deriva la única ruta canónica permitida:

```text
source_documents/blobs/sha256/<prefijo>/<sha256>.pdf
```

Antes de responder:

- se exige SHA lowercase de 64 hexadecimales;
- `logical_path` debe coincidir exactamente con el layout content-addressed;
- la ruta lexical y resuelta permanece bajo el root XDG de Source Documents;
- ningún componente del directorio ni la hoja puede ser symlink;
- la hoja debe ser regular y no un device, socket, FIFO o directory;
- se verifican permisos S2, tamaño, cabecera `%PDF-` y SHA-256;
- se abre sin seguir symlinks cuando la plataforma ofrece `O_NOFOLLOW`;
- se comparan `lstat`/`fstat`, device, inode, tamaño y timestamps alrededor de
  la lectura cuando sea viable;
- todo descriptor se cierra ante éxito, error o cancelación.

El hash se calcula por bloques acotados; no se materializa el PDF completo en
memoria para responder un rango pequeño. Sin embargo, cada solicitud de PDF,
incluidas `HEAD` y un `Range` pequeño, vuelve a recorrer el archivo completo para
validar SHA-256 antes de construir la respuesta. Esta decisión conserva la
verificación de integridad, pero su coste de lectura y CPU es proporcional al
tamaño total del PDF, no al rango solicitado.

Una mutación detectada antes de construir la respuesta produce
`integrity_error`. La identidad del descriptor también se vuelve a comprobar al
terminar el iterador. Si el cambio se detecta después de que ASGI ya envió status
y headers, no es posible sustituir la respuesta por un envelope JSON tipado: la
conexión puede terminar de forma incompleta. No se crea una copia en runtime ni
se cambia el blob.

## HTTP Range

Sólo se acepta una unidad `bytes` y un rango por request:

- `bytes=start-end`;
- `bytes=start-`;
- `bytes=-suffix`.

Se rechazan números negativos, overflow, suffix cero, fin anterior al inicio,
inicio fuera del archivo, unidad desconocida, sintaxis parcial y rangos
múltiples. Los rangos inválidos producen 416 y, cuando se conoce el tamaño,
`Content-Range: bytes */<size>`.

El servidor calcula `Content-Length` a partir de enteros validados, nunca desde
un header reflejado. Un 206 incluye `Content-Range` exacto. `ETag` se deriva del
SHA esperado y no de un path. El filename de `Content-Disposition` elimina
controles, separadores, CR/LF y caracteres de quoting peligrosos.

La lectura de la respuesta usa bloques limitados y no amplía el rango
solicitado. El parser acota `Range` a 128 caracteres y no hay soporte multipart
en S5A. Esta fase no configura un timeout de lectura ni un límite explícito de
requests concurrentes en la aplicación o en Uvicorn; se apoya únicamente en el
servidor local y en el sistema operativo. Por ello, el coste de revalidar el SHA
completo y el consumo de un descriptor por solicitud son límites operativos
conocidos, no una defensa completa contra abuso de recursos.

## Headers de respuesta

La política base del frontend es:

```text
Content-Security-Policy:
  default-src 'self';
  script-src 'self';
  style-src 'self';
  style-src-elem 'self';
  style-src-attr 'unsafe-inline';
  worker-src 'self';
  connect-src 'self';
  img-src 'self' data:;
  font-src 'self';
  object-src 'none';
  base-uri 'none';
  form-action 'none';
  frame-ancestors 'none'
X-Content-Type-Options: nosniff
Referrer-Policy: no-referrer
X-Frame-Options: DENY
Permissions-Policy:
  camera=(), microphone=(), geolocation=(), payment=(), usb=(),
  clipboard-read=(), clipboard-write=()
```

No se permite `unsafe-eval`. La excepción limitada
`style-src-attr 'unsafe-inline'` se reserva a posicionamiento dinámico de canvas,
text layer y annotation layer de PDF.js; hojas y elementos `<style>` continúan
siendo same-origin. Si la implementación demuestra que PDF.js funciona sin esa
excepción, debe retirarse. `worker-src` permanece `'self'` porque el worker se
empaqueta; `blob:` sólo podría añadirse con evidencia runtime y documentación
específica.

La política que aplica el middleware es exacta por ruta:

- HTML de `/` y `/reader`, favicon y demás rutas de frontend:
  `Cache-Control: no-cache`;
- assets bajo `/assets/`, cuyos nombres llevan hash:
  `Cache-Control: public, max-age=31536000, immutable`;
- todas las rutas `/api/`, incluido el PDF completo o parcial:
  `Cache-Control: no-store, private`.

Así, metadata, estado de lectura y bytes PDF no entran en una caché compartida;
únicamente los assets inmutables y content-addressed por nombre reciben caché
pública prolongada.

## Endurecimiento de PDF.js

El PDF es contenido no confiable aunque su hash coincida con metadata. La
configuración observable de S5A reduce superficie de ataque de esta forma:

- el worker se empaqueta en el mismo origen y CSP limita `worker-src` a
  `'self'`;
- `getDocument(...)` usa `isEvalSupported=false`, `enableXfa=false` y
  `stopAtErrors=true`;
- `PDFViewer` recibe `annotationMode=AnnotationMode.ENABLE`, no
  `ENABLE_FORMS`, por lo que muestra la capa de anotaciones sin renderizar
  formularios interactivos; el editor se desactiva con
  `annotationEditorMode=AnnotationEditorType.NONE`;
- la aplicación no construye ni inyecta un scripting manager. El código de
  soporte que pueda existir dentro de `pdfjs-dist` no queda conectado al visor
  de S5A para ejecutar acciones JavaScript del PDF;
- `enableAutoLinking=false`, `externalLinkEnabled=false` y
  `externalLinkTarget=NONE`; además, el handler del viewer cancela clicks en
  enlaces no internos;
- `getAttachmentContent` se reemplaza por una operación que no devuelve
  contenido, y la UI no ofrece ejecución ni descarga de attachments;
- CSP restringe scripts, conexiones, workers, objetos, formularios y framing al
  conjunto documentado; no concede `unsafe-eval`.

Estas medidas describen configuración y pruebas funcionales observadas, no una
garantía absoluta frente a todo PDF malicioso. S5A no incluye todavía una
campaña exhaustiva con corpus hostil ni aislamiento adicional del proceso del
navegador; una vulnerabilidad de PDF.js o del navegador sigue dentro del riesgo
residual.

El build y sus dependencias son locales. No hay fuentes remotas, collector de
analytics/telemetría, error reporting externo ni fetch a dominios de terceros.
El chunk de React conserva el identificador de API
`dangerouslySetInnerHTML` como parte de su renderer genérico, aunque el código
de MathMongo no lo importa ni lo invoca. El chunk de PDF.js conserva nombres de
eventos internos que contienen `telemetry`; no existe collector, endpoint ni
listener de aplicación para ellos. Separar los chunks permite comprobar que el
entrypoint propio no contiene ninguno de esos identificadores y que CSP impide
conexiones externas.

## Selección, búsqueda y privacidad

La query de búsqueda y el texto seleccionado pueden revelar contenido del PDF.
Ambos permanecen en memoria del navegador:

- la búsqueda usa el find controller local de PDF.js;
- no se envía query o índice al backend;
- el texto seleccionado se limita y normaliza;
- la geometría se limita a rectángulos `[0,1]` relativos a página;
- no se guardan coordenadas de screen/viewport;
- selección multipágina no produce geometría reutilizable;
- cambiar de página, rotación, versión o Document limpia la selección;
- no se usa Clipboard API ni copia automática;
- no se escribe en web storage, MongoDB, XDG, logs o URL.

Los detalles técnicos están cerrados por defecto y siguen siendo texto plano.
S5A no expone botones de highlight, underline, Annotation o Concept Linking.

## Escritura de Reading State

El único endpoint mutador acepta exactamente `{"pdf_page": <int>}`. Valida
Document PDF activo, página desde 1 y límite total cuando está disponible. La
operación pasa por `ReadingSpaceService.update_current_page`; están prohibidos
updates Mongo directos y Book page como current page.

El frontend sólo llama al PUT tras **Guardar posición**. Scroll, thumbnail,
búsqueda o `page_changed` no autoescriben. La idempotencia y conflictos siguen
los contratos S3.

## Errores y logging

Los errores públicos contienen código tipado, mensaje estable y request ID
opaco. Nunca reproducen excepciones, traceback, URI, credenciales, query Mongo,
headers completos, paths, filename sin sanear, selección, query de búsqueda o
bytes.

El log puede contener:

- request ID;
- método y ruta parametrizada;
- status;
- duración;
- `document_id` validado o parcialmente redactado;
- código público de resultado.

No registra query string completa, Range crudo fuera de diagnósticos acotados,
Mongo URI, HOME, path del blob, SHA completo si no es necesario, texto PDF o
payload de selección. `sanitize_mongo_error` se aplica antes de cualquier
mensaje relacionado con conexión.

## Imports, XDG y efectos laterales

Importar `mathmongo.advanced_reader` o crear schemas no conecta a MongoDB, abre
blobs, crea directorios, aplica índices o inicializa colecciones. La app se crea
mediante factory con base, repositorios y servicios inyectados explícitamente.

El frontend compilado es read-only dentro del paquete. Runtime no modifica
wheel/site-packages. Perfiles de navegador, bases, XDG y PDFs usados en pruebas
se crean en directorios temporales con cleanup verificable.

## Supply chain y distribución

`package-lock.json` fija dependencias e integridad. Se usa `npm ci`; no se
ejecuta `npx` para obtener herramientas faltantes, no se instalan paquetes
globales y Playwright apunta al Chrome del sistema con descarga de navegadores
deshabilitada.

El bundle debe inspeccionarse para excluir:

- CDN, URLs/fuentes remotas y fetch externo;
- `eval`, `new Function`, scripts inline innecesarios y HTML inseguro;
- Mongo URI, HOME, paths absolutos o datos de usuario;
- PDFs, blobs, `.env`, logs, caches, `node_modules` y source maps no aprobados;
- endpoints/collectors de analytics o telemetría y claves de servicios.

La presencia literal del nombre de propiedad React
`dangerouslySetInnerHTML` y de eventos internos `telemetry` de PDF.js se audita
en sus chunks separados; no se presenta como código de aplicación ni como una
llamada de red. El source y el entrypoint propios deben permanecer libres de
ambos.

Wheel y sdist incluyen HTML, JS, CSS, worker y notices/licencias. La instalación
offline se prueba sin resolver dependencias desde la red.

## Validación de seguridad prevista

Las pruebas focales deben cubrir al menos:

- import/factory sin conexión ni efectos laterales;
- host remoto, Host inválido y CORS wildcard ausente;
- ID inválido, Document ausente/web/archivado;
- metadata y errores sin paths/URI;
- blob ausente, hoja no regular, symlink y escape bloqueados;
- tamaño, cabecera y hash distintos;
- Range completo, abierto, suffix, inválido y múltiple;
- streaming acotado sin lectura completa en memoria;
- CSP y headers en frontend, API, PDF y assets;
- PUT validado y ausencia de escrituras por selección/navegación;
- scan del source y bundle por patrones prohibidos;
- navegador real sin requests remotos ni errores de consola.

Una prueba sintética no debe usar un PDF, blob o base real. No se afirma soporte
Range o selección real hasta observar requests y comportamiento en Chrome.

## Riesgo residual y límites

S5A no ofrece aislamiento contra un usuario local privilegiado, malware local,
extensiones del navegador o vulnerabilidades desconocidas de Chrome/PDF.js. No
debe exponerse mediante reverse proxy, túnel, contenedor publicado, LAN o nube.

No hay persistencia visual, autenticación multiusuario, OCR, scraping,
telemetría ni ejecución de contenido activo. Cualquier acceso remoto o
persistencia de geometría requiere una fase y threat model nuevos.
