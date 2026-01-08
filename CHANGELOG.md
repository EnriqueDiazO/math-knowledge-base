# Changelog

All notable changes to this project will be documented in this file.

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
