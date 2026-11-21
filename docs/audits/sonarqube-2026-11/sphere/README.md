# Esfera editable — registro acumulativo

Punto de partida obligatorio: `de166650`, checkpoint [cerrado](../closure/CHECKPOINT.md)
en `audit/sonarqube-2026-11`. Rama `feature/knowledge-sphere-2026-11`, creada desde
ese commit después de comprobar los cinco criterios. No se tocó main ni se hizo push.

## Contrato y decisiones

- Inspección real: `GrafoConocimiento` usa NetworkX MultiDiGraph y PyVis; el
  preview de relaciones usa PyVis. Los nodos proceden de `concepts`, el contenido
  de `latex_documents`, las relaciones de `relations` (`desde`, `hasta`, `tipo`),
  con índice único de esa terna. Las referencias Markdown no son esta colección.
  Los mapas guardados y las exportaciones antiguas siguen disponibles.
- La nueva sección «Esfera editable» comparte exactamente nodos/aristas entre
  sus dos proyecciones Plano/Esfera. No agrega conexiones por proximidad ni
  elimina conceptos. Las ediciones escriben las colecciones originales y son
  visibles al regenerar/exportar un mapa existente con los servicios habituales.
- CCv2 de Streamlit 1.67, Canvas 2D sin dependencias nuevas de ejecución/frontend.
  Se generó primero el template oficial cookiecutter/v2 Pure Typescript en un
  directorio temporal; su manifest, registro ESM y configuración de biblioteca
  Vite se adaptaron al paquete/toolchain ya instalados. El manifest real queda
  en `mathmongo/pyproject.toml`; sólo recursos generados en el directorio estático
  ya empaquetado. No se alteraron exclusiones de Sonar para esta funcionalidad.
- Posiciones unitarias Fibonacci deterministas; altas incrementales conservan
  las posiciones existentes. La ubicación elegida es presentación, conservada
  con cámara, filtros, selección y borrador en sessionStorage por un scope hash
  sin credenciales. No son relaciones ni una escritura de MongoDB. Un límite
  de almacenamiento del navegador conserva la sesión en memoria.
- Arcos de círculo máximo, desvíos tangenciales para paralelas y bucles sobre
  la superficie; se define un plano determinista para antípodas. Se dibujan sólo
  las relaciones existentes. Una única RAF, DPR máximo 2, observers/listeners
  liberados y pausa fuera de vista/pestaña oculta/movimiento reducido.
- Crear exige nombre/contenido y una Source administrada activa, revalidada
  en backend; tipo y categorías usan ConceptoBase. IDs nuevos estables derivados
  del UUID de operación; los IDs existentes nunca cambian. Las ocho relaciones
  y su dirección se validan con Relation. No hay credenciales en el navegador.
- El ledger `_knowledge_map_operations` aparece únicamente al enviar una
  intención; UUID único, hash del payload y lease de 30 segundos. Reenvíos y
  respuesta incierta reconcilian la misma identidad. Reutilizar UUID con otro
  borrador se rechaza. Un duplicado conserva datos y se puede seleccionar/conectar.
- «Crear conectado» conserva el concepto válido si el vínculo falla, informa
  parcial y permite recuperar el mismo intento. Ninguna compensación elimina
  conceptos o modificaciones ajenas. Se reutiliza el insert auditado; su único
  parámetro opcional nuevo marca la propiedad del contenido para recuperar una
  confirmación perdida, sin cambiar el comportamiento de los llamadores anteriores.
- Edición compara un hash BSON de metadata/contenido y CAS atómico de documento
  completo con `$expr/$$ROOT`, incluyendo campos desconocidos. Sólo `$set` de
  campos editables y marcadores/fecha. Sin transacciones ni replica set. Si la
  segunda escritura falla, ficha válida + resultado parcial, sin revertir datos
  ajenos. Conflicto conserva borrador; adoptar la revisión actual exige revisarla.
- Renderizado de datos por textContent/propiedades DOM/canvas, sin HTML de usuario.
  La notación LaTeX se conserva literalmente en ficha/editor; la edición/lectura
  avanzada y los renderizadores matemáticos existentes se abren mediante la
  navegación real del proyecto. No se incorporó un segundo editor enriquecido.

## Evidencia en curso

`evidence/sonar/sphere-2026-11/` es privado/ignorado. El harness real
`tests/run_knowledge_map_e2e.py` posee su mongod/dbpath, base, puertos, XDG y
Streamlit; verifica persistencia consultando MongoDB después del navegador y
retira únicamente esos recursos. Los errores iniciales de harness/estilos se
conservaron en logs de desarrollo y se están corrigiendo antes del cierre.

Fuentes primarias consultadas: [CCv2 1.67](https://docs.streamlit.io/develop/api-reference/custom-components/st.components.v2.component),
[template oficial](https://github.com/streamlit/component-template/tree/main/cookiecutter/v2),
[`$expr` de MongoDB](https://www.mongodb.com/docs/manual/reference/operator/query/expr/).
