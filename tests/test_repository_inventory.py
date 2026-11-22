"""Provenance distinctions required by the ongoing maintainability review."""

import pytest

from scripts.repository_inventory import category


@pytest.mark.parametrize(('path', 'expected'), [
    ('editor/cuaderno_page.py', 'maintained'),
    ('frontend/advanced-reader/src/app/App.tsx', 'maintained'),
    ('frontend/advanced-reader/tests/e2e-runner.mjs', 'test'),
    ('tests/source_catalog_migration_fakes.py', 'test'),
    ('mathmongo/advanced_reader/static/assets/app.js', 'generated'),
    ('quarto_book_build/_book/site_libs/bootstrap/bootstrap-icons.css', 'generated'),
    ('frontend/advanced-reader/node_modules/mathlive/mathlive.mjs', 'dependency'),
    ('mathdbmongo/lib/python3.10/site-packages/tool.py', 'dependency'),
    ('evidence/sonar/coverage.xml', 'evidence'),
    ('sonar-project.properties', 'configuration'),
    ('Makefile', 'configuration'),
    ('docs/SONARQUBE.md', 'documentation'),
])
def test_inventory_keeps_source_tests_dependencies_and_generated_output_distinct(path, expected):
    """Size reports must not suggest deleting generated/dependency bytes as own code."""
    assert category(path)[0] == expected
