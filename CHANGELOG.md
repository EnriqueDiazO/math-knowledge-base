# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)
and this project adheres to Semantic Versioning.

---
## [Unreleased] — 2026-01-21

### Added

* Fully functional **Weekly Review (V5) CRUD** inside the Notebook module:

  * Explicit loading of existing weekly reviews via a recent-weeks selector.
  * Proper **editing** of previously created weekly reviews (no duplicated records).
  * Safe deletion of existing weekly reviews.
* **Weekly Review CSV export (MVP)** following the same UX pattern as Worklog/Backlog:

  * *Select from Recents* mode.
  * *Filtered Query* mode (date range, ISO year/week, free-text search).
  * Row-level selection via `st.data_editor`.
* Display of derived weekly metrics:

  * Real hours (aggregated from Worklog).
  * Completed tasks count (from Backlog).
  * Number of worklog entries.
  * Short preview of recent activities.
* Optional **manual override** for weekly metrics (real hours / tasks done), while keeping derived metrics as the default source of truth.
* Functional CRUD for **Deliverables**:

  * Loading of recent deliverables.
  * Direct editing of existing deliverables.
  * CSV export with filters and row selection.

### Fixed

* Fixed a critical issue where the Weekly Review editor **did not load original values** when switching between weeks:

  * Explicit synchronization between Streamlit `session_state` and MongoDB documents.
  * Removal of "sticky" values caused by reused widget keys.
* Corrected Weekly Review task completion counts:

  * Preferential use of `done_at` timestamps when available.
  * Controlled fallback to `updated_at` for legacy backlog items.
* Eliminated false-positive editor warnings (red underlines) caused by static analysis when using optional dataframes with `locals()`.

### Improved

* Full UX consistency across **Worklog**, **Backlog**, **Weekly Review**, and **Deliverables**:

  * Unified patterns for recents, filtering, selection, and CSV export.
* Clearer conceptual separation between:

  * **Derived data** (worklog / backlog metrics).
  * **Manual narrative data** (weekly review content).
* Improved weekly traceability by consolidating narrative, metrics, and activities into a single coherent view.

### Technical

* Introduced internal helper functions for *best-effort* weekly metric computation.
* Explicit and controlled use of `session_state` for reliable editor synchronization in Streamlit.
* All changes kept minimal and localized, avoiding large refactors or navigation regressions.
* Changes validated using:

  * `git apply --check`
  * `python -m compileall`

### Design Notes

* Weekly Review is now treated as a **narrative + analytical artifact**, not as a primary source of metrics.
* Automatically derived metrics remain the default and authoritative source; manual overrides are explicit and auditable.
* Stability, predictability, and cognitive clarity were prioritized over enterprise-style complexity.




## [Unreleased] — 2026-01-09

### Added
- Automated generation of `_quarto.yml` for Quarto Book exports, including:
  - `format.html` with TOC and numbered sections
  - `format.pdf` using `lualatex`
  - Centralized LaTeX preamble via `include-in-header`
- Explicit support for bibliography processing in Quarto Books:
  - `bibliography: references.bib`
  - `citeproc: true`
- Robust custom LaTeX environment `algoritmo` for shell and code blocks:
  - Safe handling of active characters (`>>`, `<<`) under `babel(spanish)`
  - Consistent rendering using `tcolorbox` + `listings`
- Enhanced syntax highlighting for code blocks:
  - `bash`
  - `python`
  - Extensible to additional languages (e.g. C)
- Dedicated Quarto installation script:
  - `scripts/install_quarto.sh`
  - Architecture-aware (`amd64`, `arm64`)
  - Optional SHA256 verification
  - Version-pinned installation for reproducible builds

### Improved
- Reliability of Quarto PDF builds by aligning generated `_quarto.yml`, LaTeX preamble, and export pipeline
- Visual quality of code blocks in PDFs (improved colors, clearer token distinction)
- Separation between mathematical environments (`definition`, `theorem`, etc.) and procedural/code environments (`algoritmo`, `lstlisting`)

### Fixed
- Quarto/Pandoc compilation failures caused by:
  - Active characters in `babel(spanish)`
  - Shell redirection operators (`>>`) inside code blocks
- Missing or overwritten fields in auto-generated `_quarto.yml`
- Undefined LaTeX environments in Quarto Book builds
- Inconsistent bibliography resolution across generated chapters

### Technical
- `_write_book_quarto_yml` now emits a complete and explicit Quarto configuration
- Improved diagnosability of LaTeX errors caused by symbol-level typos (e.g. `\apha` vs `\alpha`)
- Established a single source of truth for Quarto configuration and LaTeX styling

### Documentation
- Updated README to require Quarto installation via `scripts/install_quarto.sh`
- Added explicit warnings about LaTeX symbol typos that can break Quarto builds

### Design Notes
- Quarto Book export is treated as a first-class build target
- LaTeX correctness is enforced as a hard requirement
- Minor LaTeX symbol errors can invalidate the entire build and must be carefully reviewed

---

## [Unreleased] — 2026-01-08

### Added
- Cognitive **Relation Tutor** for semantic relations between concepts.
- Verification **checklists** per relation type (`equivalente`, `implica`, `requiere_concepto`, `contradice`, `contra_ejemplo`).
- Tri-state evaluation (`Sí / No / No sé`) for essential and optional criteria.
- **Quality feedback** with semantic warnings based on checklist completion.
- **Strict mode** option to block saving relations unless essential criteria are satisfied.
- Contextual **visual preview** of relations with configurable hop depth.
- Mini **subgraph preview** to validate local consistency and detect cycles early.
- Toggleable display of **Titles / IDs / Both** for concepts and relations.
- Export of relation preview and subgraph as **JSON**.
- Downloadable **HTML map** for visual previews.

### Improved
- Relation assignment workflow is now educational and self-validating.
- Graph preview readability by replacing internal IDs with human-readable titles.
- Early detection of questionable or underspecified relations before persistence.
- UX consistency between preview graphs and full visualization graphs.

### Technical
- Centralized relation semantics via `RELATION_CHECKLIST`.
- Session-scoped checklist state (non-persistent by design).
- Modular preview graph generation aligned with main visualization engine.
- Updated Makefile targets for development workflow consistency.

### Design Notes
- Checklist responses are intentionally **not persisted** to the database.
- Relation tutor acts as a **cognitive scaffold**, not as stored metadata.
- Separation preserved between conceptual validation and canonical data.

---

## [Unreleased] — 2026-01-07

### Added
- Dual graph construction modes:
  - **Exploratory mode**: allows placeholder nodes when no concept filters are applied.
  - **Strict mode**: enforces concept-type filters and omits relations that introduce out-of-scope nodes.
- Placeholder nodes for missing concepts, rendered in very light gray.
- Debug logging for omitted relations due to missing nodes.

### Changed
- Graph construction logic now respects UI filters for concept types.
- Relations no longer implicitly force unrelated nodes into filtered graphs.
- Visual distinction between real concepts and placeholder nodes.

### Fixed
- Bug where relations caused nodes to appear even when filtered out in the UI.
- Inconsistent graph behavior when filtering by concept type.

### Notes
- Placeholder nodes are only introduced when no concept-type filters are applied.
- This change aligns backend graph logic with UI filtering semantics.
