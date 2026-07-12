# Auditoría de vistas previas PDF generadas

## Alcance y causa raíz

Add Concept, Edit Concept, Cornell y CPI generan correctamente sus PDFs con los
renderers LaTeX existentes. El problema estaba en la entrega del resultado: los
flujos solicitaban al navegador abrir una ruta local. Firefox puede impedir el
acceso a archivos del runtime de otra aplicación por su aislamiento, aunque el
PDF sea válido.

P1 sustituye esa entrega por un visor dentro de la página de Streamlit. No añade
un servidor HTTP, contenido JavaScript, un iframe de datos ni una implementación
propia de PDF.js. Tampoco crea una segunda copia permanente del archivo.

## Arquitectura compartida

`editor/pdf_preview.py` es la única implementación del ciclo de vida del preview
generado. Los cuatro flujos siguen esta secuencia:

1. invalidan el preview anterior de su namespace;
2. preparan la ruta controlada y eliminan sólo el PDF obsoleto y auxiliares LaTeX
   conocidos;
3. ejecutan el generador existente;
4. validan y leen el resultado una sola vez;
5. guardan un payload inmutable con bytes, nombre de descarga, SHA-256 e identidad
   de contexto;
6. pasan esos bytes a `st.pdf` y al botón de descarga;
7. permiten cerrar el preview sin afectar los otros flujos.

La ruta se comprueba contra una raíz mutable controlada. Se rechazan escapes,
symlinks, archivos ausentes, resultados que no sean regulares, archivos vacíos,
lecturas incompletas o inestables y contenido sin cabecera `%PDF-`. Los mensajes
de error no incluyen rutas absolutas, bytes ni contenido LaTeX.

El visor usa `st.pdf(pdf_bytes, height=800, key=...)`. Su clave deriva del
namespace, del contexto y del SHA-256, por lo que un rerun conserva el mismo
preview y un PDF nuevo obtiene una identidad nueva. `Descargar PDF` recibe
exactamente los mismos bytes ya validados; no vuelve a leer el archivo.

## Estado, aislamiento y fallos

Los namespaces son independientes:

- `pdf_preview_add_concept_*`;
- `pdf_preview_edit_concept_*`;
- `pdf_preview_cornell_*`;
- `pdf_preview_cpi_*`.

La identidad opaca del contexto incluye la base y la entidad relevante. Un cambio
de base, concepto o nota invalida el payload en vez de mostrar un documento de un
contexto anterior. Sólo se conserva el preview actual de cada flujo.

El estado se limpia antes de compilar. Por ello, un error LaTeX, un PDF ausente o
una validación fallida no puede reutilizar el preview anterior. Si LaTeX produce
warnings pero también un PDF válido, el visor se mantiene y los diagnósticos se
presentan por el canal ya existente. Si el componente del visor falta o falla, la
interfaz muestra un error accionable y conserva la descarga de los bytes válidos.

## Flujos cubiertos

| Flujo | Generador existente | Ubicación | Entrega P1 |
| --- | --- | --- | --- |
| Add Concept | exportador de concepto | política temporal/XDG existente | visor y descarga, sin guardar el concepto |
| Edit Concept | exportador de concepto | política temporal/XDG existente | visor y descarga, sin modificar el concepto |
| Cornell | renderer Cornell | `runtime/cornell_preview/cornell_preview.pdf` | visor, diagnósticos y descarga |
| CPI | renderer CPI | `runtime/cpi_preview/cpi_preview.pdf` | visor, diagnósticos y descarga |

La preparación conserva archivos ajenos y elimina únicamente el PDF estable y
los auxiliares cuyo stem corresponde al preview. No modifica MongoDB, conceptos,
Sources ni References.

## Dependencia del visor

Streamlit 1.55.0 expone `st.pdf`, pero carga su componente mediante el extra
oficial `pdf`. Por ello el proyecto declara `streamlit` con `extras = ["pdf"]` en
`pyproject.toml` y `streamlit[pdf]` en `requirements.txt`. Ese extra instala
`streamlit-pdf`. La dependencia se restringe a la serie oficial 1.x porque la
serie 2.0 usa el registro de componentes v2 y no carga sus assets con Streamlit
1.55.0; la comprobación aislada confirma `streamlit-pdf` 1.0.8. No se añade un
componente alternativo ni se actualiza la versión de Streamlit como parte de P1.

## Pruebas y límites

Las pruebas P1 verifican validación de archivos, lectura y SHA, namespaces,
limpieza y persistencia de estado, igualdad de bytes entre visor y descarga,
errores del componente y la integración de Add/Edit/Cornell/CPI. Una comprobación
estática acotada impide reintroducir mecanismos de apertura local en esos módulos
y comprueba que el extra oficial permanezca declarado.

P1 sólo visualiza PDFs generados por MathMongo. No almacena ni visualiza PDFs
bibliográficos asociados a Sources, no crea Documents o `source_documents`, no
introduce anotaciones, subrayados, ReadingNote o ConceptEvidenceLink y no cambia
el modelo de datos. Esas capacidades pertenecen a S2/S3 y quedan fuera de esta
fase.
