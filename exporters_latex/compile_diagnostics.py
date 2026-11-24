"""Small actionable summaries of compiler diagnostics; never infer storage support."""

import re


def compilation_failure_message(log: str) -> str:
    """Explain known fatal diagnostics while retaining the full original log separately."""
    package = re.search(r"File [`']([^`'\n]+\.(?:sty|cls))' not found", log)
    if package:
        return (
            f"Falta el paquete LaTeX «{package[1]}». Instálalo en el equipo que compila o revisa "
            "su declaración en Código LaTeX y vuelve a compilar. El documento se conserva."
        )
    environment = re.search(r"Environment ([A-Za-z@*][A-Za-z0-9@*_-]*) undefined", log)
    if environment:
        return (
            f"El entorno «{environment[1]}» no está definido. Añade su definición al preámbulo "
            "en Código LaTeX y vuelve a compilar. Consulta Detalles de compilación; el documento se conserva."
        )
    if "Undefined control sequence" in log:
        return (
            "Hay un comando LaTeX sin definir. Consulta Detalles de compilación, añade su macro "
            "o el paquete necesario en Código LaTeX y vuelve a compilar. El documento se conserva."
        )
    return (
        "No se pudo compilar este documento. Consulta Detalles de compilación, corrige la fuente "
        "y vuelve a compilar. El documento se conserva."
    )
