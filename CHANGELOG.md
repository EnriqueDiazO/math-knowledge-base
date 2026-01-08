# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)
and this project adheres to Semantic Versioning.

---

## [Unreleased] — 2026-01-07

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
