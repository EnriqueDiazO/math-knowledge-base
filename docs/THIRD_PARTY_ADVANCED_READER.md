# Terceros del Advanced Reader — S5A

## Alcance del registro

Este inventario cubre las dependencias añadidas o fijadas específicamente para
el prototipo Advanced Reader. Las versiones frontend son las resueltas por
`package-lock.json`; las versiones Python son las resueltas dentro de
`mathdbmongo`. Los paquetes históricos de MathMongo se documentan en sus
contratos correspondientes y no se duplican aquí.

No se usa CDN ni se descarga código en runtime. `node_modules` y las
dependencias de build/test no se distribuyen en wheel o sdist; sólo se incluyen
los assets compilados necesarios, el worker PDF.js y los avisos de licencia.

## Runtime Python

| Dependencia | Versión | Licencia | Uso en S5A | Fuente oficial |
| --- | ---: | --- | --- | --- |
| FastAPI | 0.139.0 | MIT | factory ASGI, routing, validación HTTP y respuestas tipadas | [PyPI](https://pypi.org/project/fastapi/0.139.0/) |
| Uvicorn | 0.51.0 | BSD-3-Clause | servidor ASGI loopback del launcher explícito | [PyPI](https://pypi.org/project/uvicorn/0.51.0/) |
| Starlette | 1.3.1 | BSD-3-Clause | capa ASGI/HTTP subyacente fijada por FastAPI | [PyPI](https://pypi.org/project/starlette/1.3.1/) |

Restricciones declaradas por el proyecto: FastAPI `>=0.115,<1.0` y Uvicorn
`>=0.34,<1.0`. Las versiones de la tabla son la resolución concreta usada para
S5A. El Advanced Reader sigue usando Pydantic, PyMongo y los servicios existentes
de MathMongo; no introduce una segunda capa de persistencia.

## Runtime frontend

| Dependencia | Versión | Licencia | Uso en S5A | Fuente oficial |
| --- | ---: | --- | --- | --- |
| React | 19.2.7 | MIT | composición y lifecycle de la aplicación local | [npm](https://www.npmjs.com/package/react/v/19.2.7) |
| React DOM | 19.2.7 | MIT | montaje del árbol React en el documento local | [npm](https://www.npmjs.com/package/react-dom/v/19.2.7) |
| pdfjs-dist | 6.1.200 | Apache-2.0 | render PDF, worker, text/annotation layers, thumbnails, navegación y búsqueda | [npm](https://www.npmjs.com/package/pdfjs-dist/v/6.1.200) |

`pdfjs-dist` se consume mediante sus APIs públicas. No se copia sin revisión el
viewer demo completo. El worker se empaqueta en el mismo origen; no se usa el
worker de un CDN ni se habilita ejecución de JavaScript embebido en el PDF.

## Build, tipos, lint y pruebas frontend

| Dependencia | Versión | Licencia | Uso en S5A | Fuente oficial |
| --- | ---: | --- | --- | --- |
| Vite | 8.1.4 | MIT | dev server loopback y build de assets con hash | [npm](https://www.npmjs.com/package/vite/v/8.1.4) |
| TypeScript | 6.0.3 | Apache-2.0 | tipos y typecheck del frontend | [npm](https://www.npmjs.com/package/typescript/v/6.0.3) |
| @vitejs/plugin-react | 6.0.3 | MIT | transformación React durante dev/build | [npm](https://www.npmjs.com/package/@vitejs/plugin-react/v/6.0.3) |
| @eslint/js | 10.0.1 | MIT | configuración y reglas JavaScript recomendadas de ESLint | [npm](https://www.npmjs.com/package/@eslint/js/v/10.0.1) |
| ESLint | 10.7.0 | MIT | análisis estático JavaScript/TypeScript | [npm](https://www.npmjs.com/package/eslint/v/10.7.0) |
| typescript-eslint | 8.64.0 | MIT | parser y reglas TypeScript para ESLint | [npm](https://www.npmjs.com/package/typescript-eslint/v/8.64.0) |
| eslint-plugin-react-hooks | 7.1.1 | MIT | reglas de Hooks React | [npm](https://www.npmjs.com/package/eslint-plugin-react-hooks/v/7.1.1) |
| eslint-plugin-react-refresh | 0.5.3 | MIT | validación de límites Fast Refresh en desarrollo | [npm](https://www.npmjs.com/package/eslint-plugin-react-refresh/v/0.5.3) |
| globals | 17.7.0 | MIT | globals de navegador/test para ESLint | [npm](https://www.npmjs.com/package/globals/v/17.7.0) |
| Vitest | 4.1.10 | MIT | runner de pruebas unitarias frontend | [npm](https://www.npmjs.com/package/vitest/v/4.1.10) |
| @testing-library/react | 16.3.2 | MIT | pruebas de componentes desde la perspectiva del usuario | [npm](https://www.npmjs.com/package/@testing-library/react/v/16.3.2) |
| @testing-library/jest-dom | 6.9.1 | MIT | matchers DOM para Vitest | [npm](https://www.npmjs.com/package/@testing-library/jest-dom/v/6.9.1) |
| @testing-library/user-event | 14.6.1 | MIT | simulación de interacciones de usuario en pruebas DOM | [npm](https://www.npmjs.com/package/@testing-library/user-event/v/14.6.1) |
| jsdom | 29.1.1 | MIT | DOM acotado para pruebas unitarias | [npm](https://www.npmjs.com/package/jsdom/v/29.1.1) |
| @playwright/test | 1.61.1 | Apache-2.0 | E2E contra Chrome del sistema, sin descargar navegadores | [npm](https://www.npmjs.com/package/@playwright/test/v/1.61.1) |
| @types/node | 26.1.1 | MIT | declaraciones TypeScript para APIs Node usadas por build y tests | [npm](https://www.npmjs.com/package/@types/node/v/26.1.1) |
| @types/react | 19.2.17 | MIT | declaraciones TypeScript de React | [npm](https://www.npmjs.com/package/@types/react/v/19.2.17) |
| @types/react-dom | 19.2.3 | MIT | declaraciones TypeScript de React DOM | [npm](https://www.npmjs.com/package/@types/react-dom/v/19.2.3) |

Playwright es sólo una herramienta de pruebas. S5A usa
`/usr/bin/google-chrome` o la ruta del Chrome del sistema detectada y configura
la omisión de descargas de navegador. Chromium, Firefox y WebKit de Playwright
no forman parte del repositorio, caché de release, wheel, sdist ni bundle.

## Gestor y reproducibilidad

El gestor frontend es npm 11.12.1 sobre Node 24.15.0. `package.json` y
`package-lock.json` se versionan juntos; `npm ci` debe fallar si divergen. No se
usa `npm install -g`, `sudo npm`, `npx` con descarga implícita, Corepack para
resolver un package manager no fijado ni `npm audit fix --force`.

El lockfile fija también dependencias transitivas e integridades. Este documento
registra las dependencias directas y la dependencia backend transitiva de
seguridad/HTTP más relevante, Starlette. Antes de un release, el inventario del
lock debe compararse con los notices empaquetados para detectar licencias o
versiones transitivas nuevas.

## Obligaciones y notices

- MIT: conservar aviso de copyright y texto de licencia en las copias
  redistribuidas.
- BSD-3-Clause: conservar copyright, condiciones y disclaimer; no usar nombres
  de autores para endorsement.
- Apache-2.0: conservar licencia, avisos aplicables y marcas de cambios cuando
  corresponda; respetar disposiciones de patentes y `NOTICE` si el paquete lo
  proporciona.

El build de producción debe publicar un directorio de notices/licencias junto a
los assets del Advanced Reader. Wheel y sdist deben incluirlo. La minificación
no autoriza a retirar banners o avisos exigidos; cuando un banner no pueda
conservarse en cada chunk, el notice agregado debe ser accesible dentro de la
distribución.

## Exclusiones

S5A no incorpora PSPDFKit/Nutrient, PDF.js Express, librerías comerciales de
visor, kits grandes de UI, fuentes remotas, collectors de analytics/telemetría
o servicios hosted. PDF.js conserva nombres internos de eventos de telemetría,
pero MathMongo no registra listeners ni endpoints para ellos. Tampoco
redistribuye Google Chrome: el navegador es una precondición del E2E local, no
una dependencia del producto.

El bundle se inspecciona para confirmar que no contiene `node_modules`, source
maps no aprobados, PDFs de prueba, blobs, datos MongoDB, `.env`, cachés, logs,
rutas de usuario o recursos remotos.
