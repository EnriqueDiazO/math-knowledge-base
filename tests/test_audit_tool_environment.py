"""Validate the HTML notebook toolchain after its parser dependency update."""

from bs4 import BeautifulSoup
from nbconvert import HTMLExporter
from nbformat.v4 import new_code_cell
from nbformat.v4 import new_markdown_cell
from nbformat.v4 import new_notebook
from nbformat.v4 import new_output


def test_notebook_html_preserves_markdown_mathematics_and_output():
    """HTML export and SoupSieve selection retain content without starting a kernel/server."""
    notebook = new_notebook(cells=[
        new_markdown_cell("# Validación local\n\nMatemáticas: $x^2 + \\alpha$."),
        new_code_cell("1 + 1", execution_count=1, outputs=[
            new_output("execute_result", data={"text/plain": "2"}, execution_count=1),
        ]),
    ])
    html, _resources = HTMLExporter().from_notebook_node(notebook)
    document = BeautifulSoup(html, "html.parser")
    assert document.select_one(".jp-RenderedMarkdown h1").get_text().strip().startswith("Validación local")
    assert "x^2" in document.select_one(".jp-RenderedMarkdown").get_text()
    assert "2" in document.select_one(".jp-OutputArea-output").get_text()
