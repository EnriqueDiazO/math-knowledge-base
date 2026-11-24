"""Real isolated compilation; never read user documents or write outside tmp_path."""

from exporters_latex.sandbox import compile_document


def test_visual_latex_structure_compiles_with_real_styles_and_a_tikz_preview():
    """The same canonical runner produces real PDF/PNG from nested semantic bodies."""
    source = r"""\documentclass{article}
\usepackage{notes}
\usepackage{mathmongo-macros}
\begin{document}
\begin{context}
\begin{definition}{Idea visual}
Una definición $\frac{1}{2}$.
\begin{remark}{}Una nota anidada.\end{remark}
\end{definition}
\begin{tikzpicture}\draw (0,0)--(1,1);\end{tikzpicture}
\end{context}
\end{document}"""
    result = compile_document(source, raster=True)
    assert result.status == "ready", result.diagnostic
    assert result.pdf.startswith(b"%PDF-") and result.png.startswith(b"\x89PNG\r\n\x1a\n")


def test_authored_input_cannot_read_a_host_file_or_write_a_new_host_file(tmp_path):
    """A real TeX input attempt fails even though the caller can read that path."""
    private = tmp_path / "private.tex"
    private.write_text("HOST_PRIVATE_SENTINEL")
    result = compile_document(
        r"\documentclass{article}\begin{document}\input{" + str(private) + r"}\end{document}"
    )
    assert result.status == "failed" and not result.pdf
    assert "HOST_PRIVATE_SENTINEL" not in result.diagnostic
    assert private.read_text() == "HOST_PRIVATE_SENTINEL"
    output = tmp_path / "forbidden.tex"
    result = compile_document(
        r"\documentclass{article}\begin{document}\newwrite\file\immediate\openout\file="
        + str(output)
        + r"\immediate\write\file{unwanted}\end{document}"
    )
    assert result.status == "failed" and not output.exists()


def test_asset_parent_paths_are_rejected_without_touching_the_parent(tmp_path):
    """The staging contract rejects traversal before invoking any tool."""
    result = compile_document("Test", {"../outside.tex": b"bad"})
    assert result.status == "invalid"


def test_sandbox_clears_credentials_has_no_host_network_and_no_writable_directory(
    tmp_path, monkeypatch
):
    """A real isolated process cannot contact even an owned host loopback server."""
    import socket
    import subprocess

    from exporters_latex.sandbox import OUTPUTS
    from exporters_latex.sandbox import _command

    inputs, outputs = tmp_path / "inputs", tmp_path / "outputs"
    inputs.mkdir()
    outputs.mkdir()
    (outputs / "empty").mkdir()
    for name in OUTPUTS:
        (outputs / name).touch()
    private = tmp_path / "private.txt"
    private.write_text("PRIVATE_PROBE")
    monkeypatch.setenv("MATHMONGO_PRIVATE_PROBE", "PRIVATE_PROBE")
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen()
        port = server.getsockname()[1]
        code = "\n".join(
            [
                "import os,socket,errno",
                "assert os.environ.get('MATHMONGO_PRIVATE_PROBE') is None",
                f"assert not os.path.exists({str(private)!r})",
                "s=socket.socket();s.settimeout(.3)",
                f"assert s.connect_ex(('127.0.0.1',{port})) != 0",
                "for path in ['/work/unexpected','/tmp/unexpected','/inputs/unexpected']:",
                " try: open(path,'w')",
                " except OSError as error: assert error.errno == errno.EROFS",
                " else: raise AssertionError('writable directory')",
                "print('isolated')",
            ]
        )
        result = subprocess.run(
            _command(inputs, outputs, "/usr/bin/python3", ["-c", code]),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "isolated"
    assert private.read_text() == "PRIVATE_PROBE"
