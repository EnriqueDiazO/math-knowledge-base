# Identidad matemática de MathMongo en pantalla

La fuente acordada por el usuario es `templates_latex/miestilo.sty`, en este
repositorio. Se contrastaron sus declaraciones de cajas (líneas 205–219) y alias
(224–237). No se recibió otro estilo diferente que sustituya esa referencia.
Las plantillas LaTeX no se han modificado.

## Original y adaptación

Los nombres son de **xcolor**, no de CSS. La instalación local de xcolor declara
`purple` en RGB como `.75,0,.25`; `violet` es `.5,0,.5`. El primero se convierte
en **#BF0040**, distinto de la palabra CSS `purple` (#800080). `orange` es
`1,.5,0`, `green` es `0,1,0`, `teal` es `0,.5,.5`. Se ejecutó un documento mínimo
con `\extractcolorspec` y `\convertcolorspec … {HTML}` mediante `pdflatex` en
un directorio temporal. La evidencia completa está en
`evidence/sonar/xcolor-conversions.json`; incluye también las mezclas.

`x!p` mezcla p % de x con blanco, y `x!p!black` con negro. Por ejemplo,
`purple!5` → #FCF2F5 y `purple!60!black` → #730026.
`white!100!black` produce **blanco**: no se interpretó como un borde negro.

| Tipo / símbolo | Nombre xcolor y RGB web original | Fondo / borde originales de la caja | Acento de pantalla | Fondo tenue / borde de pantalla |
|---|---|---|---|---|
| Definición · D | blue · #0000FF | #F2F2FF / #0000BF | #8ABEFF | #102A42 / #426A96 |
| Teorema · T | red · #FF0000 | #FFF2F2 / #A60000 | #FF9B9B | #292A38 / #89505D |
| Corolario · C | green · #00FF00 | #F2FFF2 / #009900 | #93DDA5 | #142E32 / #42785D |
| Lema · L | purple · #BF0040 | #FCF2F5 / #730026 | #ED9ABB | #2C2539 / #87516D |
| Proposición · P | orange · #FF8000 | #FFF9F2 / #FFFFFF | #F0C29B | #252C33 / #8A7662 |
| Ejemplo · E | orange · #FF8000 | #FFF5EB / #FF8C1A | #FFAB58 | #2C2B2E / #9A663E |
| Nota · N | yellow · #FFFF00 | #FFFFE5 / #A6A600 | #E9D879 | #272D2C / #817844 |
| Observación · O | teal · #008080 | #F0F7F7 / #004D4D | #7ED6D0 | #122E39 / #387E80 |

Los títulos originales son blancos salvo Proposición (`orange!85!black`,
#D96C00). En pantalla usan el acento de su familia. Estas variantes se eligieron
para el fondo azul existente #091A27 y el documento #102737; **no son una nueva
definición de los colores LaTeX**. El fondo tenue se restringe al encabezado y
las etiquetas; los párrafos largos y las demostraciones conservan el documento
oscuro y texto claro. Las pruebas verifican contraste de texto y acentos ≥ 4,5:1
en sus superficies efectivas. Esto no sustituye una auditoría WCAG completa.

La copia `quarto_book/styles/miestilo.sty` tiene diferencias reales: Ejemplo
usa gris y algunos títulos/bordes cambian. Se conserva como estilo de ese
exportador. No se mezclaron sus grises con la referencia elegida para la web.
`codepurple`, Boot* y DI* son otras familias del archivo y tampoco se utilizaron
para decidir el color de Lema.

## Semántica y organización

- `editor/ui/concept_types.json` es la única tabla de valores de tipo. El
  adaptador TS genera variables `--concept-<tipo>-accent/background/border`.
  `concept-types.css` consume esas variables; no repite valores hexadecimales.
- Se conservan los alias ingleses, españoles y `cth…`. **remark → Nota**;
  `observation`/`observacion` → Observación. La selección de inserción ofrece
  una sola opción por familia, más Demostración neutral.
- Editor, lectura, previsualización, etiquetas de resultados y leyenda/nodos
  comparten esa tabla. Proposición tiene rombo y P, naranja suave y borde doble
  en su caja; Ejemplo tiene cuadrado y E, con naranja más intenso.
- Los nodos usan el acento y formas; los rótulos visibles incluyen el símbolo.
  Las regiones representan **áreas temáticas** mediante contorno discontinuo
  y colores de la paleta del espacio, independientes del tipo de sus miembros.
- Los colores de notas, Cornell/CPI y estados no se sustituyeron por esta tabla.
  Un error utiliza mensaje, icono de advertencia, fondo y borde propios; una
  caja Teorema tiene encabezado matemático T y cuerpo normal.
- Navegación, documento y controles reutilizan `study_theme.json`; sus reglas
  de profundidad están en `study/surfaces.css`. Las herramientas se agrupan
  por texto, historial, resultados, fórmulas y representación. Las reglas nuevas
  del editor están en `document-tools.css`, separadas de tipos y superficies.
- MathLive usa sus fuentes matemáticas locales y sus partes/API públicas. Se
  corrigió la dependencia accidental de estilos del mapa: la superficie del
  documento importa explícitamente sus estilos, también al abrir una nota
  directamente. El teclado recibe el tema fuera del diálogo.
- Interacciones de 140 ms; `prefers-reduced-motion: reduce` desactiva transiciones
  y animaciones. El fondo espacial se reserva a Inicio/Espacios.
- En 390 px, las herramientas forman una fila desplazable (58 px de alto) y
  las acciones de guardado quedan en el flujo después del documento. La captura
  previa mostró un solapamiento; ahora se comprueba que el borde superior de
  las acciones quede después del borde inferior del editor en ambos navegadores.
  Las capturas previas se conservaron en `evidence/sonar/react-checkpoint/narrow-before-*.png`.

La serialización conserva la fuente original. Las cajas con opciones LaTeX
explícitas permanecen como bloques de fuente protegida: el adaptador acotado no
puede interpretar estilos TeX arbitrarios y no los reemplaza por la paleta web.
Su estilo completo se conserva para exportar. Esto es una limitación visible,
no una previsualización fiel de todas las personalizaciones TeX.

## Regresiones y evidencia visual

`concept-types.test.ts` comprueba alias, las ocho familias, contraste, aislamiento
respecto a estados/CPI, conservación exacta del LaTeX y opciones personalizadas.
`test_mathematical_type_identity.py` guarda cada tipo en Mongo temporal, lo
recupera y reintenta la misma operación sin duplicar identidades. Observación
faltaba en el contrato canónico de siete tipos; ahora es un octavo valor válido.

La prueba en navegador detectó una conversión involuntaria: el LF de texto
LaTeX dentro de una caja se convertía en `hardBreak` al reconciliar el DOM tras
abrir MathLive y terminaba serializado como `\\`. El adaptador representa el
LF de prosa como espacio, conforme a su significado en LaTeX, y conserva los
bytes originales en la procedencia. No modifica LF de código ni fórmulas. La
prueba vuelve a abrir fuente después de teclado y recarga y exige igualdad
exacta, sin normalizar la comparación.

La muestra se abre en **Ajustes → Ver los tipos matemáticos y su paleta**
(`/study/settings/appearance`). Muestra originales y variantes, ocho bloques y
fórmulas reales. No escribe en la biblioteca.

Las capturas y resultados están bajo
`evidence/sonar/independent-study/{chrome,firefox}/`:

| Evidencia | Qué permite comprobar |
|---|---|
| `all-types-reading.png` | Ocho cajas, etiquetas y colores originales/pantalla. |
| `editor-types-wide.png`, `editor-types-keyboard.png` | Editor amplio, foco de teclado, grupos y MathLive real. |
| `editor-types-narrow.png`, `all-types-narrow.png` | Ventana de 390 × 844, sin desbordamiento horizontal. |
| `sphere-all-types.png` | Nueve conceptos temporales, ocho tipos y leyenda compartida. |
| `palette-browser.json` | Versiones, zoom 100 %, escala 1, 1440 × 1080/390 × 844, colores CSS calculados, ausencia de errores y solicitudes externas. |
| `palette-draft-stages.json` | Estado visual, después del teclado y después de recargar; conserva el LaTeX sin publicar la muestra. |

El runner comprueba primero el recorrido funcional y sus conteos exactos
(1 nota, 1 concepto, 1 anotación, 2 evidencias). **Después** añade ocho conceptos
de muestra con el servicio canónico. Al terminar verifica 9 conceptos y sólo
1 nota guardada: el borrador visual no se publicó. Todo pertenece a procesos,
puertos, directorios y base Mongo temporales, eliminados al cerrar el runner.

```bash
.venv/bin/python tests/run_independent_study_e2e.py --browser=chrome --palette
.venv/bin/python tests/run_independent_study_e2e.py --browser=firefox --palette
```

La comparación Sonar, las revisiones exactas y los pendientes de migración
se registran en [MIGRATION_CHECKPOINT.md](MIGRATION_CHECKPOINT.md).
