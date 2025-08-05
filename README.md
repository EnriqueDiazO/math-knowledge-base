# 📚 Math Knowledge Base
1
> **Estado:** Versión Beta (0.1.0b1)  
> Plataforma diseñada para registrar, visualizar y exportar definiciones, teoremas, ejemplos y conceptos matemáticos en LaTeX.

---

## 🚀 Objetivo

Crear una **base de datos personalizable** de conocimiento matemático:
- Captura de entradas mediante interfaz Streamlit.
- Almacenamiento estructurado en MongoDB.
- Exportación automática a LaTeX y generación de PDFs.
- Visualización de relaciones entre conceptos usando grafos.

## 🎨 Estilo visual de conceptos matemáticos

Cada concepto registrado puede ser exportado a un archivo `.tex` y compilado como PDF, con formato estilizado gracias al uso del paquete [coloredtheorem](https://github.com/joaomlourenco/coloredtheorem).

- Los entornos como **Definición**, **Teorema**, **Ejemplo**, etc., se muestran dentro de cajas coloreadas.
- Se usa el archivo personalizado `exporters/templates/miestilo.sty` para controlar la presentación.
- Puedes definir conceptos sin numeración usando entornos como `\begin{cthdefinicion*}{...}`.

Esto permite generar documentos matemáticos visualmente atractivos directamente desde la base de datos.

### 📄 Generación de PDF desde la interfaz

La aplicación incluye funcionalidad para generar PDFs directamente desde los formularios de conceptos:

- **Botón "📄 Generar y abrir PDF"** en los formularios de "Add Concept" y "Edit Concept"
- **Generación automática** usando `pdflatex` con el mismo estilo que `ExportadorLatex`
- **Apertura automática** en el navegador web
- **Almacenamiento persistente** en `~/math_knowledge_pdfs/`
- **Nombres descriptivos** de archivos: `{id}_{tipo}.pdf`
- **Permisos correctos** para acceso desde navegador (644 para archivos, 755 para directorio)

Los PDFs generados usan **exactamente el mismo estilo** que el exportador existente:
- **Archivos de estilo**: `miestilo.sty` y `coloredtheorem.sty`
- **Formato LaTeX**: Mismo preámbulo y estructura que `ExportadorLatex`
- **Entornos matemáticos**: Compatibles con `coloredtheorem` (cajas coloreadas)
- **Metadatos**: Misma presentación de referencias y comentarios

---

## 📦 Estructura del proyecto

- `editor/` — Aplicación Streamlit para captura y consulta (incluye generación de PDF).
- `parsers/` — Funciones para agregar archivos md a la base de datos.
- `mathdabase/` — Conexión y gestión de la base de datos MongoDB y clases principales.
- `exporters/` — Scripts para generar documentos LaTeX/PDF. Incluye integración con `miestilo.sty` y `coloredtheorem`.
- `schemas/` — Esquemas relacionados para validar los campos de los conceptos matemáticos.
- `visualizations/` — Visualización de grafos matemáticos.

---

## ⚙️ Requisitos

- Ubuntu 20.04, 22.04 o similar (recomendado).
- Python 3.10+ (recomendado: 3.10.14 o 3.11.6).
- MongoDB instalado y activo (`sudo apt install mongodb` y `sudo systemctl start mongod`).
- Instalación completa de LaTeX (`sudo apt install texlive-full`) para exportar PDFs correctamente.
- `make` instalado (habitual en sistemas Linux).
- Git, pip.

> ⚠️ No está pensado aún para Windows puro; se recomienda WSL si se usa Windows.

---

## 🛠️ Instalación rápida

```bash
# Clonar el proyecto
git clone https://github.com/EnriqueDiazO/math-knowledge-base.git
cd math-knowledge-base

# Crear y activar entorno virtual
python -m venv mathdbmongo
source mathdbmongo/bin/activate

# Instalar dependencias
pip install -r requirements.txt

# Instalar el proyecto en modo editable
pip install -e .

# (Opcional) Verifica que pdflatex esté disponible
pdflatex --version

# Iniciar MongoDB
make start

# Lanzar la aplicación Streamlit
make run

# (Opcional) Exportar un concepto de prueba como PDF estilizado
python exporters/exportadorlatex.py --id <concept_id>

# (Opcional) Probar la generación de PDF desde la interfaz
# Abre la aplicación y usa el botón "📄 Generar y abrir PDF" en cualquier formulario

