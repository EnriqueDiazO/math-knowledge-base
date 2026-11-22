# Commits locales del cierre estricto

Orden desde `41c25714`; el commit documental de checkpoint se identifica en la rama de funcionalidad por su punto de partida. Los fallos antes/después y las ejecuciones se relacionan en CHECKPOINT.md y README.md.

| Commit | Cambio | Pruebas modificadas / verificación |
|---|---|---|
| `e3129ac7` | chore(audit): recover the authoritative corpus and record strict closure criteria | Controles de instalación/build y suites afectadas; ver CHECKPOINT.md. |
| `bde6e983` | fix(migration): bind approved plans to content rather than local file metadata | `tests/test_migration_plan_identity.py` |
| `dcef32dc` | fix(audit): enforce production invariants without removable assertions | `tests/test_audit_production_guards.py`; `tests/test_fresh_database_lifecycle_e2e.py`; `tests/test_legacy_concept_source_link_e2e.py` |
| `7a71a60a` | fix(export): publish private PDFs and preserve colliding QMD identities | `tests/test_audit_export_integrity.py` |
| `e393939c` | build(images): qualify Pillow 13 with its supported Streamlit and PDF stack | `tests/test_teaching_environment_files.py` |
| `71e46fdf` | build(security): update DNS and Tornado for the supported Python profile | Controles de instalación/build y suites afectadas; ver CHECKPOINT.md. |
| `cbcd0765` | build(tools): patch pytest and HTML parsing with locked build tools | `tests/test_audit_tool_environment.py` |
| `3cf3b45c` | fix(quality): reject invalid reports and verify remaining resource failure paths | `tests/test_audit_production_guards.py`; `tests/test_migration_plan_identity.py`; `tests/test_quality_lifecycle.py`; `tests/test_sonar_execution.py`; `tests/test_sonar_http_contracts.py`; `tests/test_sonar_tooling.py` |
| `1d1a5c95` | refactor(runtime): select the qualified environment for commands and browser tests | `tests/run_advanced_reader_e2e.py`; `tests/run_local_runtime_e2e.py` |
| `f6614c05` | fix(parsing): bound adversarial matching while preserving mathematical input | `tests/test_audit_regex_boundaries.py` |
| `04dc4c9e` | test(compatibility): validate the new environment and real unsent form drafts | `tests/run_theme_draft_e2e.py`; `tests/test_advanced_reader_packaging.py`; `tests/test_concept_linking_apptest.py`; `tests/test_concept_linking_ui.py`; `tests/test_internal_pdf_preview_static.py`; `tests/test_local_runtime_makefile.py`; `tests/test_mathmongo_theme_apptest.py` |
| `d2ff0bbd` | fix(reader): name and verify the keyboard-scrollable PDF region | `tests/local_runtime_browser_probe.mjs` |
| `2c452994` | refactor(markdown): parse line metadata with an explicit linear scan | Controles de instalación/build y suites afectadas; ver CHECKPOINT.md. |
| `5021bbd1` | build(dev): declare the notebook verification imports in both installation paths | Controles de instalación/build y suites afectadas; ver CHECKPOINT.md. |
| `3d6e0021` | fix(build): normalize resource text linearly and verify nullable schema contracts | `frontend/advanced-reader/tests/text-normalization.test.ts`; `tests/test_audit_schema_contracts.py` |
