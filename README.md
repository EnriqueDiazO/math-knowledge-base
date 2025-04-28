# 📚 Math Knowledge Base

> **Estado:** Versión Beta (0.1.0b1)  
> Plataforma diseñada para registrar, visualizar y exportar definiciones, teoremas, ejemplos y conceptos matemáticos en LaTeX.

---

## 🚀 Objetivo

Crear una **base de datos personalizable** de conocimiento matemático:
- Captura de entradas mediante interfaz Streamlit.
- Almacenamiento estructurado en MongoDB.
- Exportación automática a LaTeX y generación de PDFs.
- Visualización de relaciones entre conceptos usando grafos.

---

## 📦 Estructura del proyecto

- `app/` — Aplicación Streamlit para captura y consulta.
- `conversion/` — Utilidades para transformar LaTeX, JSON, Mongo.
- `db/` — Conexión y gestión de la base de datos MongoDB.
- `export/` — Scripts para generar documentos LaTeX/PDF.
- `visualizacion/` — Visualización de grafos matemáticos.
- `plantillas/` — Plantillas LaTeX utilizadas para la exportación.
- `notebooks/` — Exploraciones y experimentos.
- `.vscode/` — Configuración de entorno de desarrollo.

---

## ⚙️ Requisitos

- Ubuntu 20.04, 22.04 o similar (recomendado).
- Python 3.10+ (recomendado: 3.10.14 o 3.11.6).
- MongoDB instalado y activo (`sudo systemctl start mongod`).
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

# Iniciar MongoDB
make start

# Lanzar la aplicación Streamlit
make run

