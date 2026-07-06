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

- Long-form mathematical documents.
- Research notes and lecture material.
- Thesis-style compilations.

### ⚙️ Quarto Installation (Mandatory, Script-Based)

Quarto is not assumed to be installed on the system.

To guarantee reproducibility, Quarto must be installed using the provided script:

```bash
scripts/install_quarto.sh
```

This script:

- Downloads the official Quarto distribution.
- Installs it in a controlled manner.
- Can be verified with `quarto --version` and `quarto check`.

The complete installation sequence is documented below.

## 📦 Project Structure

- `editor/` — Streamlit application for data entry, editing, querying, export/import, and PDF generation.
- `editor/cuaderno_page.py` — Notebook/Cuaderno workflow: diary notes, worklog, backlog, weekly reviews, deliverables, and Kanban.
- `editor/utils/` — Database ZIP export/import helpers.
- `mathdatabase/` — MongoDB connection, database management, and core classes.
- `parsers/` — Functions for importing Markdown/YAML concept files into the database.
- `exporters_latex/` — LaTeX/PDF export tools.
- `exporters_quarto/` and `scripts/export_quarto_book.py` — Quarto book export tools.
- `schemas/` — Pydantic schemas used to validate mathematical concept fields.
- `visualizations/` — Interactive mathematical graph visualizations.

---

## ⚙️ Requirements

- Ubuntu 20.04, 22.04, or similar (recommended).
- Python 3.10+ (recommended: 3.10.14 or 3.11.6).
- MongoDB installed and running.
- Full LaTeX installation (`texlive-full`) for correct PDF export.
- ChkTeX (`chktex`) for static LaTeX analysis in notebook exports.
- `make`, Git, pip.

> ⚠️ Not yet intended for native Windows use; WSL is recommended.

---

## 🛠️ Installation

The application needs four things before running:

1. MongoDB running locally.
2. A Python virtual environment with the project dependencies.
3. LaTeX/Quarto if you want PDF and book exports.
4. MongoDB collections/indexes initialized for the database you will use.

### 1. Clone the project

```bash
git clone https://github.com/EnriqueDiazO/math-knowledge-base.git
cd math-knowledge-base
```

### 2. Install system dependencies

On Ubuntu/Debian, install MongoDB, Python tooling, Make, Git, and LaTeX. Package names may vary depending on your distro and MongoDB installation method.

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git make texlive-full
```

Start MongoDB:

```bash
make start
```

You can also check it directly:

```bash
sudo systemctl status mongod
```

### 3. Create the Python environment

The project convention is to use a virtual environment named `mathdbmongo`.

```bash
python3 -m venv mathdbmongo
source mathdbmongo/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
```

### 4. Install and verify Quarto and ChkTeX

Quarto is used for book-level exports. Install it with the project script:

```bash
bash scripts/install_quarto.sh
quarto --version
quarto check
```

ChkTeX is used for static LaTeX analysis in notebook exports. Install it with the project script:

```bash
./scripts/install_chktex.sh
```

Manual Ubuntu/Debian alternative:

```bash
sudo apt install -y chktex
```

Verify LaTeX and ChkTeX too:

```bash
pdflatex --version
command -v chktex
chktex --version
```

### 5. Initialize MongoDB collections and indexes

Run this for every database where you want the full GUI features. The app commonly uses `mathmongo` by default, and imported/active working databases often use names like `MathV0`.

```bash
python scripts/install_cuaderno_mode.py --mongo-uri mongodb://127.0.0.1:27017 --db mathmongo
```

For `MathV0`:

```bash
python scripts/install_cuaderno_mode.py --mongo-uri mongodb://127.0.0.1:27017 --db MathV0
```

This command is non-destructive. It creates missing Notebook/graph-map collections and indexes without deleting existing data. Core concept/relation indexes are also created automatically when the app opens a `MathMongo` connection.

The full database flow uses:

- `concepts`
- `relations`
- `latex_documents`
- `latex_notes`
- `worklog_entries`
- `backlog_items`
- `weekly_reviews`
- `deliverables`
- `knowledge_graph_maps`
- `media_assets`

The installer also creates the portable media directory:

- `media/images`

Images uploaded from concepts or Cuaderno notes are stored as local files under `media/images` and referenced from MongoDB with relative paths such as `media/images/figure.png`. Database export/import includes both the `media_assets` collection and the `media/` tree, so backups remain portable across machines and database names.

### 6. Run the Streamlit app

```bash
make run
```

Or directly:

```bash
source mathdbmongo/bin/activate
streamlit run editor/editor_streamlit.py
```

The app opens at `http://localhost:8501`.

### 7. Optional desktop shortcut

```bash
chmod +x scripts/make_desktop_shortcut.sh
./scripts/make_desktop_shortcut.sh
```

## 🔁 Updating a Database (MathV0)

To update a database, follow these steps:

1. In the database you want to update, go to **Navigation → Settings**.

2. Select **Clear All Data**.  
   This will delete all existing content while keeping the database name **MathV0**.

3. Then go to **Database Import** and import the database using the name **MathV0**.  
   Fill in all required fields, and make sure you use the name **MathV0**.

4. To enable notebook mode, run the following command in your terminal:

   ```bash
   python scripts/install_cuaderno_mode.py --mongo-uri mongodb://127.0.0.1:27017 --db MathV0
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

## 🔁 Database Export & Import (Portability and Versioning)

Math Knowledge Base includes **explicit database export and import capabilities**, designed to support **portability, versioning, backups, and long-term reproducibility**.

These features are intentionally **manual and explicit**: no automatic synchronization or silent overwrites are performed.

---

### 📤 Database Export

The application allows exporting the **entire MongoDB database** used by Math Knowledge Base into a single ZIP archive.

**Key characteristics:**

- Export is **read-only** and does not modify the database.
- All collections are exported as **JSON files**, one file per collection.
- Expected project collections are included even when empty, including `knowledge_graph_maps`.
- MongoDB-specific types are safely normalized:
  - `ObjectId` → string
  - `datetime` → ISO 8601 strings
- A `metadata.json` file is included, containing:
  - Export timestamp
  - Collection names and document counts

This makes the export:
- Fully versionable (e.g. via Git or external storage),
- Portable across machines,
- Independent of the runtime environment.

### 🗺️ Knowledge graph maps

Concept maps edited from **Knowledge Graph Visualization** are stored in the `knowledge_graph_maps` collection and are included in full database exports/imports.

Each saved map keeps:
- generation filters (`sources`, concept types, relation types, max depth),
- nodes and edges,
- edited node positions and fixed-node state,
- physics, layout, and edge-control settings,
- node/edge text sizing,
- tags and descriptive metadata.

The `graph_state` payload is exported without trimming so restored maps preserve the visual editing state.

Typical use cases include:
- Creating snapshots before major refactors,
- Sharing datasets between machines,
- Long-term archival of research states.

---

### 📥 Database Import (Create-New-Database Only)

The import mechanism is intentionally conservative.

**Important design rule:**
> Imports always create or populate a **new MongoDB database**.  
> Existing databases are never overwritten automatically.

**Import workflow:**

1. Upload a previously exported ZIP archive.
2. The system **inspects the archive** before importing:
   - Validates format
   - Displays collection names and document counts
3. The user explicitly specifies a **new database name**.
4. Only after confirmation, the data is imported into that new database.

This design:
- Prevents accidental data loss,
- Enables side-by-side comparison of database versions,
- Supports safe experimentation and rollback.

---

### 🧠 Recommended Naming Convention

While MongoDB allows arbitrary database names, the following convention is recommended:

- `MathV0` — primary active database
- `MathV0_snapshot_YYYYMMDD` — frozen snapshots
- `MathV0_import_YYYYMMDD` — imported states
- `Math_exp_<topic>` — experimental or research-specific databases

Adopting explicit naming conventions improves traceability and reduces cognitive overhead when working with multiple database versions.

---

### 🎯 Design Philosophy

Database export and import are treated as **first-class operations**, not hidden utilities.

The goal is to ensure that:
- Every database state is explainable,
- Transitions between states are intentional,
- Mathematical knowledge remains durable beyond a single machine or session.

This approach favors **correctness, transparency, and reproducibility** over automation.




## 🆕 Recent Additions to the Math Knowledge Base (January 21, 2026)

This section summarizes the **most recent functional additions** to the Math Knowledge Base, extending the core concept-management platform with structured workflow, planning, and traceability features.

---

## 🗒️ Notebook (Cuaderno) System

A new **Notebook-oriented workflow** has been introduced to complement concept capture with operational and reflective tooling. This subsystem is designed to record *what was done, why it was done, and what comes next*, while remaining tightly integrated with the mathematical knowledge base.

### 🧾 Worklog

* Daily chronological logging of work activities.
* Text-based entries with optional hour tracking.
* Filtering and querying by date ranges and keywords.
* CSV export with row selection.

### 📋 Backlog

* Structured task tracking linked to projects and objectives.
* Status-based workflow (e.g., To Do, In Progress, Done).
* Query and export capabilities consistent with Worklog.
* Acts as the primary source of truth for task completion metrics.

---

## 📅 Weekly Review (V5)

The **Weekly Review** module provides a structured, week-level synthesis layer that connects daily execution (Worklog) and task completion (Backlog) with narrative reflection and planning.

### Core Capabilities

* **Add Weekly Review**

  * Create a weekly review indexed by ISO year and ISO week.

* **Edit Weekly Review**

  * Load any existing weekly review from recent weeks.
  * Editor fields are populated directly from persisted MongoDB documents.

* **Delete Weekly Review**

  * Safe deletion with explicit user confirmation.

* **Export Weekly Reviews (CSV)**

  * Same interaction model as Worklog and Backlog.
  * Selection from recent weeks or filtered queries.

### Structured Narrative Fields

* Weekly objectives
* Wins and achievements
* Blockers and risks
* Plan for the following week

### Integrated Metrics

Weekly Reviews are enriched with **automatically derived metrics**:

* **Real hours worked** (aggregated from Worklog entries).
* **Tasks completed** (derived from Backlog items marked as Done).
* **Activity summary** (preview of recent worklog tasks).

An optional **manual override** mechanism allows correcting these metrics when historical data is incomplete, while preserving derived values as the default.

---

## 📦 Deliverables Tracking

The **Deliverables** module has been expanded into a first-class, editable artifact type:

* Load and edit existing deliverables.
* Track deliverables by project, status, and type.
* Export deliverables to CSV using the same selection and filtering patterns used elsewhere in the system.

---

## 🔄 Unified User Experience

All Notebook-related modules (Worklog, Backlog, Weekly Review, Deliverables) now share a **common interaction model**:

* Recent items view
* Explicit load into editor
* Safe edit and save
* CSV export with row-level selection

This consistency reduces cognitive load and supports long-term, incremental knowledge accumulation.

---

## 🧠 Design Philosophy

* Mathematical concepts remain the **core canonical objects** of the system.
* Notebook artifacts provide **context, traceability, and planning**, not competing sources of truth.
* Quantitative metrics are derived from atomic records whenever possible.
* Narrative reflection and planning are stored explicitly and independently.

---

These additions position the Math Knowledge Base not only as a repository of mathematical knowledge, but also as a **research and study companion** capable of supporting sustained, multi-week intellectual work.
