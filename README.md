# 📚 Math Knowledge Base

> **Status:** Beta Version (0.1.0b1)  
> A platform designed to register, visualize, and export mathematical definitions, theorems, examples, and concepts in LaTeX.

---

## 🚀 Objective

To build a **customizable mathematical knowledge database** that supports:
- Entry capture via a Streamlit interface.
- Structured storage in MongoDB.
- Automatic LaTeX export and PDF generation.
- Visualization of relationships between concepts using graphs.

---

## 🎨 Visual Styling of Mathematical Concepts

Each registered concept can be exported to a `.tex` file and compiled into a PDF, using a styled format powered by the  
[coloredtheorem](https://github.com/joaomlourenco/coloredtheorem) package.

- Environments such as **Definition**, **Theorem**, **Example**, etc., are rendered inside colored boxes.
- A custom style file, `exporters/templates/miestilo.sty`, is used to control presentation.
- You may define unnumbered concepts using environments like `\begin{cthdefinicion*}{...}`.

This enables the generation of visually appealing mathematical documents directly from the database.

---

### 📄 PDF Generation from the Interface

The application includes built-in functionality to generate PDFs directly from concept forms:

- **“📄 Generate and open PDF” button** available in both *Add Concept* and *Edit Concept* forms.
- **Automatic generation** using `pdflatex`, matching the style used by `ExportadorLatex`.
- **Automatic opening** in the web browser.
- **Persistent storage** in `~/math_knowledge_pdfs/`.
- **Descriptive filenames**: `{id}_{type}.pdf`.
- **Correct permissions** for browser access (644 for files, 755 for the directory).

Generated PDFs use **exactly the same style** as the existing exporter:
- **Style files**: `miestilo.sty` and `coloredtheorem.sty`.
- **LaTeX format**: Same preamble and structure as `ExportadorLatex`.
- **Mathematical environments**: Fully compatible with `coloredtheorem` (colored boxes).
- **Metadata**: Same presentation for references and comments.

---

### 📘 Book-Level Export with Quarto

In addition to single-concept PDF generation, the project supports book-level exports using Quarto Book.

Quarto is used to compile complete mathematical books from the knowledge base, allowing concepts to be organized into chapters and sections while preserving the same LaTeX visual identity.

This enables:

- Long-form mathematical documents

- Research notes and lecture material

- Thesis-style compilations

### ⚙️ Quarto Installation (Mandatory, Script-Based)

Quarto is not assumed to be installed on the system.

To guarantee reproducibility, Quarto must be installed using the provided script:

```bash
scripts/install_quarto.sh
```

This script:

- Downloads the official Quarto distribution

- Installs it in a controlled manner

- Verifies the installation with:

## 📦 Project Structure

- `editor/` — Streamlit application for data entry and querying (includes PDF generation).
- `parsers/` — Functions for importing Markdown files into the database.
- `mathdabase/` — MongoDB connection, database management, and core classes.
- `exporters/` — Scripts for generating LaTeX/PDF documents, including integration with `miestilo.sty` and `coloredtheorem`.
- `schemas/` — Schemas used to validate mathematical concept fields.
- `visualizations/` — Mathematical graph visualizations.

---

## ⚙️ Requirements

- Ubuntu 20.04, 22.04, or similar (recommended).
- Python 3.10+ (recommended: 3.10.14 or 3.11.6).
- MongoDB installed and running.
- Full LaTeX installation (`texlive-full`) for correct PDF export.
- `make`, Git, pip.

> ⚠️ Not yet intended for native Windows use; WSL is recommended.

---

## 🛠️ Quick Installation

```bash
git clone https://github.com/EnriqueDiazO/math-knowledge-base.git
cd math-knowledge-base

python -m venv mathdbmongo
source mathdbmongo/bin/activate

pip install -r requirements.txt
pip install -e .

pdflatex --version

# Instala Quarto usando el script oficial del proyecto
bash scripts/install_quarto.sh

# Verifica instalación
quarto --version
quarto check

# Corremos la app
make start
make run
```

---

## 📚 Adding References

You can add references using standard BibTeX format:

```bibtex
@book{knuth1984texbook,
  author    = {Donald E. Knuth},
  title     = {The TeXbook},
  year      = {1984},
  publisher = {Addison-Wesley},
  edition   = {Revised},
  volume    = {A},
  pages     = {1--483},
  isbn      = {0-201-13448-9},
  doi       = {10.5555/53924},
  url       = {https://ctan.org/pkg/texbook}
}
```