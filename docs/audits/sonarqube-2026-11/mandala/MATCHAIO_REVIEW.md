# Matchaio: comparación selectiva, 24 de noviembre de 2026

Repositorio observado: `/home/enriquedo/PersonalProjects/Matchaio`, revisión
`8194e17`. Inspección sin cambios en ese repositorio. El experimento ejecutó sus
seis archivos Vitest en una copia temporal independiente de `src`, configuración
y dependencias: **31 pruebas aprobadas**. Sin instalaciones ni servicios contra
datos personales. Evidencia local: `evidence/sonar/matchaio-2026-11-24/`.

## Qué existe realmente

React/Vite/Konva organiza objetos de dibujo y bloques de documento. FastAPI y
Python convierten figuras a TikZ; SQLite mantiene su workspace. `mathText` es
una cadena LaTeX con presentación KaTeX y edición mediante **textarea**, no un
árbol editable de átomos matemáticos. El editor permite selección geométrica,
movimiento, duplicación, capas, formas, flechas, texto y recursos. La paleta
marca explícitamente diversos gráficos como `stub` o `unsupported`; mostrarlos
en un botón no demuestra implementación.

Archivos contrastados:

- `frontend/src/components/{DocumentEditor,DocumentBlockRenderer,DiagramCanvas}.tsx`:
  composición por bloques, canvas y edición inline; Escape cancela, Enter o
  Ctrl+Enter confirman el texto matemático. El canvas conserva la selección de
  objetos, no demuestra selección visual de subexpresiones.
- `ContextualToolbar.tsx`, `SuggestionBox.tsx`, `DiagramTypePalette.tsx`:
  herramientas según selección, inserción progresiva y capacidades pendientes.
- `frontend/src/model/{documentBlocks,diagramTypes,documentPersistence}.ts`:
  bloques/objetos propios, procedencia y `rawMathcha`, revisiones/recuperación.
- `frontend/src/components/MathTextOverlay.tsx`: KaTeX sobre contenido matemático.
- `frontend/src/App.tsx`: atajos geométricos protegidos al escribir en un control.
- `src/tikz/{matchaio_exporter,text_converter}.py`, `src/export/latex_exporter.py`:
  exportación de figuras y wrapper LaTeX. No equivalen al contrato de documentos
  académicos arbitrarios de MathMongo.
- `frontend/src/test/*.test.*`, `README.md`, `LICENSE`, `package-lock.json` y
  `docs/mathcha2tikz_reuse_decision.md`: pruebas, alcance y procedencia declarados.

## Licencias y decisión de reutilización

El `LICENSE` raíz de Matchaio declara MIT. La inspección del código actual y de
las licencias instaladas directas encuentra MIT (React, Konva, KaTeX, Vite y
adaptadores), ISC (lucide-react) y Apache-2.0 (TypeScript). Los nombres/versiones
efectivas están en `dependency-licenses.json`; no se deducen de rangos de npm.
Matchaio separa `app_extracted` y `external` del núcleo: no se reutilizan bundles
propietarios ni se presume que la licencia raíz los cubra. Su tercero
`mathcha2tikz` tiene un aviso MIT propio y una revisión de procedencia separada.

**Decisión:** reutilizar ideas de interacción y escribir implementaciones propias
sobre MathLive/Tiptap. Cero código copiado, cero paquetes de Matchaio incorporados,
cero modelo SQLite o Konva añadido a MathMongo. Por ello no se incorpora una
cadena transitiva de dependencias de Matchaio. Una futura incorporación de código
o biblioteca necesitaría revisar sus archivos y avisos concretos; esta inspección
no la autoriza automáticamente.

## Matriz de capacidades

| Capacidad | Matchaio observado | MathMongo antes de este lote | Ventaja / decisión |
|---|---|---|---|
| Fórmula visual editable | Texto LaTeX + KaTeX; textarea inline | MathLive editable | Ya disponible: conservar MathLive |
| Fracciones, índices, radicales anidados | LaTeX escrito en textarea | MathLive; plantillas usan `replaceAll` | Mejorable: inserción por selección, con regresión |
| Matrices de tamaño variable | Tablas de documento; no constructor matemático demostrado | Botón fijo 2×2; MathLive tiene soporte matricial | Ausente en la interfaz: constructor acotado sobre MathLive |
| Sistemas, alineación y delimitadores | LaTeX escrito; no edición reversible demostrada | Código permitido; accesos visuales limitados | Añadir plantillas buscables, sin otro parser |
| Selección de subexpresión | Selección geométrica de objetos; textarea para texto | Selección MathLive existente | Exponer su uso y conservar el cursor al usar herramientas |
| Herramientas contextuales | Según objeto seleccionado | Barra de texto y fórmulas; historial de texto | Añadir historial matemático explícito del campo activo |
| Paleta progresiva | SuggestionBox y selector de tipo | Botones fijos y teclado MathLive | Búsqueda de estructuras sin saturar la barra |
| Copiar/pegar | JSON/objetos y textarea; no portapapeles matemático estructurado demostrado | MathLive y fuente LaTeX | Conservar; no inventar una ventaja de Matchaio |
| Deshacer/rehacer subexpresiones | No historial matemático equivalente demostrado | MathLive lo implementa; barra muestra historial Tiptap | Exponer comandos MathLive; nunca usar historial de texto para anunciar deshacer fórmula |
| Desconocidos/históricos | `rawMathcha`, fidelidad y procedencia | Fuente LaTeX original y bloques protegidos | Conservar contrato MathMongo; formatos diferentes |
| TikZ visual | Editor geométrico y exportación de figuras | Código protegido, vista aislada y exportación | Potencial futuro; no prioritario en este corte |
| Macros/entornos arbitrarios | Sin equivalencia documental general demostrada | Código canónico, macros, TikZ y compilación aislada | No sustituirlo por JSON/HTML de Matchaio |
| Persistencia y revisiones | Workspace SQLite y revisión propia | MongoDB, CAS y borradores por biblioteca | Arquitectura incompatible; reutilizar servicios existentes |
| Funciones/3D/plots | Muchos tipos anunciados como pendientes | PGFPlots mediante fuente protegida | No importar placeholders como capacidades nuevas |

## Tres mejoras seleccionadas

1. **Inserción localizada y herramientas de fórmula activa.** Problema:
   `DocumentEditor.insertTemplate` utiliza `replaceAll` y puede destruir el resto
   de una expresión. La selección contextual de Matchaio es una referencia de
   interacción, pero la corrección utiliza `replaceSelection` y el historial de
   MathLive instalado. Coste pequeño; riesgo de perder selección al enfocar un
   control. Pruebas: selección, inserción anidada, deshacer/rehacer, otra fórmula
   y bloques históricos intactos en ambos navegadores.
2. **Paleta de estructuras con búsqueda.** Las paletas de Matchaio justifican
   organizar opciones progresivamente. MathMongo ya tiene el teclado completo;
   faltan accesos localizables a sistemas, alineación, delimitadores y operadores.
   Implementación independiente y pequeña, sin favoritos/globales ni otro motor.
   Pruebas: filtro, teclado, inserción, LaTeX válido y cancelación sin mutaciones.
3. **Matrices configurables.** El 2×2 fijo de MathMongo limita una capacidad que
   MathLive ya ofrece. La idea de construcción parametrizada se toma de sus
   herramientas de inserción; **no se atribuye a Matchaio un editor matricial que
   no se encontró**. Reutilizar MathLive y generar `pmatrix`/`bmatrix`/`vmatrix`
   acotados; conservar originales y abrir código cuando no sea reversible.
   Pruebas: tamaños no cuadrados, límites, selección, guardar/recargar y PDF.

Las implementaciones y experimentos se registrarán al verificarse. Este documento
es el checkpoint de auditoría y selección, no una afirmación de implementación.
Continúan Cornell/CPI y la matriz de migración; no se retira código histórico.
