# Editor visual y esfera de estudio — continuación

Partida comprobada: `cf1ffc9c`, rama `feature/knowledge-sphere-2026-11`, árbol
limpio. Se conserva el checkpoint y la auditoría previa; no se reinicia su revisión.

## Evidencia e implementación por lotes

1. El Canvas conserva altura 470 fija y su ResizeObserver sólo cambia anchura.
   La ficha limita el contenido a 180 px y el editor se aloja en aside de 300 px.
   No hay renderizador matemático web ni editor documental visual: los avanzados
   actuales usan ACE y LaTeX canónico; Cornell/CPI aportan contratos de entornos
   y exportación PDF reutilizables, no un editor WYSIWYG.
2. No se atribuye un fallo de guardado al textarea sin reproducirlo. Se ejecuta
   el harness existente antes de cambios, con MongoDB, puertos y archivos propios.
3. Se localizó «Slowly oscillating shift» en el ZIP ya autorizado: copia privada,
   sin publicar su cuerpo. Contiene definition con título obligatorio entre llaves,
   arrays con columnas TeX avanzadas y figura TikZ. Debe preservarse íntegramente;
   las construcciones no soportadas se mostrarán localmente con acceso a fuente.
4. Orden: documento visual y borradores → espacio/lectura → arrastre/relaciones →
   vistas guardadas/áreas/pendientes → verificación real y comparación de calidad.

Las regiones usarán únicamente categorías elegidas explícitamente como áreas en
la vista. No se inferirán temas de autores ni se creará una taxonomía automática.
Los pendientes serán marcadores explícitos de estudio, no conceptos vacíos.
