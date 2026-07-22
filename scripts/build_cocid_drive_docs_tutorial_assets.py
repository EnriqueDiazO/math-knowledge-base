#!/usr/bin/env python3
"""Generate local, privacy-safe Drive/Docs teaching illustrations."""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from mathmongo.paths import get_runtime_dir
from mathmongo.paths import validate_mutable_path

CANVAS = (1600, 900)
BACKGROUND = "#f6f8fb"
INK = "#17233c"
MUTED = "#667085"
BLUE = "#2563eb"
PALE_BLUE = "#eaf2ff"
GREEN = "#168a5b"
YELLOW = "#f4b400"
RED = "#dc4c3f"

ASSET_SPECS: dict[str, dict[str, str]] = {
    "drive_01_nuevo.png": {
        "title": "+ Nuevo en Drive",
        "caption": "Desde aquí se crean carpetas, documentos y cargas.",
        "alt_text": "Vista ilustrativa de Drive con el botón más Nuevo señalado.",
    },
    "drive_02_crear_carpeta.png": {
        "title": "Crear una carpeta",
        "caption": "Usa nombres breves, claros y consistentes.",
        "alt_text": "Menú Nuevo con Nueva carpeta y un campo para escribir su nombre.",
    },
    "drive_03_subir_archivo.png": {
        "title": "Subir un archivo",
        "caption": "El archivo queda almacenado en la carpeta seleccionada.",
        "alt_text": "Archivo PDF entrando a una carpeta desde la opción Subir archivo.",
    },
    "docs_01_crear_y_renombrar.png": {
        "title": "Crear y renombrar",
        "caption": "Renombra el documento antes de comenzar.",
        "alt_text": "Documento en blanco con su nombre superior y el cursor de edición señalados.",
    },
    "docs_02_barra_de_herramientas.png": {
        "title": "Edición básica",
        "caption": "La barra controla la presentación del texto.",
        "alt_text": "Barra ilustrativa con estilo, fuente, negrita, alineación y lista.",
    },
    "docs_03_compartir_permisos.png": {
        "title": "Compartir con cuidado",
        "caption": "Asigna el permiso mínimo necesario.",
        "alt_text": "Botón Compartir y selector de roles Lector, Comentador y Editor.",
    },
}


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    family = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    try:
        return ImageFont.truetype(family, size=size)
    except OSError:
        return ImageFont.load_default()


def _rounded(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    *,
    fill: str,
    outline: str | None = None,
    width: int = 2,
    radius: int = 20,
) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def _label(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    *,
    size: int = 34,
    color: str = INK,
    bold: bool = False,
    anchor: str | None = None,
) -> None:
    draw.text(xy, text, fill=color, font=_font(size, bold=bold), anchor=anchor)


def _badge(draw: ImageDraw.ImageDraw, xy: tuple[int, int], number: int) -> None:
    x, y = xy
    draw.ellipse((x - 31, y - 31, x + 31, y + 31), fill=BLUE, outline="white", width=5)
    _label(draw, (x, y + 1), str(number), size=30, color="white", bold=True, anchor="mm")


def _base(spec: dict[str, str], product: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", CANVAS, BACKGROUND)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 1600, 104), fill="white")
    draw.line((0, 104, 1600, 104), fill="#d8dee9", width=2)
    _label(draw, (64, 50), spec["title"], size=46, bold=True, anchor="lm")
    _label(draw, (1535, 36), f"{product} · Vista ilustrativa", size=24, color=MUTED, anchor="ra")
    _label(draw, (1535, 72), "Interfaz simplificada, sin datos reales", size=20, color=MUTED, anchor="ra")
    draw.rectangle((0, 794, 1600, 900), fill=INK)
    _label(draw, (70, 848), spec["caption"], size=33, color="white", bold=True, anchor="lm")
    return image, draw


def _drive_sidebar(draw: ImageDraw.ImageDraw, *, selected: str = "Mi unidad") -> None:
    _rounded(draw, (52, 142, 368, 270), fill="white", outline="#cdd6e3", radius=28)
    _label(draw, (93, 206), "+  Nuevo", size=39, bold=True, anchor="lm")
    for index, item in enumerate(("Mi unidad", "Compartido", "Recientes")):
        y = 342 + index * 78
        if item == selected:
            _rounded(draw, (42, y - 35, 380, y + 35), fill=PALE_BLUE, radius=18)
        _label(draw, (90, y), item, size=29, color=INK if item == selected else MUTED, anchor="lm")


def _draw_drive_01(image: Image.Image, draw: ImageDraw.ImageDraw) -> None:
    del image
    _drive_sidebar(draw)
    _label(draw, (438, 172), "Mi unidad", size=38, bold=True)
    for index, name in enumerate(("COCID_Curso_Datos", "Materiales", "Entregables")):
        x = 438 + index * 345
        _rounded(draw, (x, 246, x + 300, 392), fill="white", outline="#d6deea")
        draw.polygon(((x + 34, 288), (x + 112, 288), (x + 132, 312), (x + 266, 312),
                      (x + 266, 365), (x + 34, 365)), fill="#f7c948")
        _label(draw, (x + 30, 420), name, size=24, color=MUTED)
    _badge(draw, (337, 155), 1)
    draw.line((315, 177, 272, 214), fill=BLUE, width=8)


def _draw_drive_02(image: Image.Image, draw: ImageDraw.ImageDraw) -> None:
    del image
    _drive_sidebar(draw)
    _rounded(draw, (405, 145, 820, 548), fill="white", outline="#cbd5e1", radius=22)
    for index, item in enumerate(("Nueva carpeta", "Subir archivo", "Documento")):
        y = 216 + index * 90
        if index == 0:
            _rounded(draw, (429, y - 35, 795, y + 39), fill=PALE_BLUE, radius=15)
        _label(draw, (474, y), item, size=31, bold=index == 0, anchor="lm")
    _badge(draw, (807, 183), 1)
    _rounded(draw, (885, 234, 1500, 545), fill="white", outline="#cbd5e1", radius=25)
    _label(draw, (930, 290), "Nueva carpeta", size=37, bold=True)
    _label(draw, (930, 356), "Nombre", size=24, color=MUTED)
    _rounded(draw, (930, 388, 1450, 460), fill="white", outline=BLUE, width=4, radius=12)
    _label(draw, (958, 425), "COCID_Curso_Datos", size=29, anchor="lm")
    _badge(draw, (1468, 389), 2)


def _draw_drive_03(image: Image.Image, draw: ImageDraw.ImageDraw) -> None:
    del image
    _drive_sidebar(draw)
    _rounded(draw, (405, 150, 830, 470), fill="white", outline="#cbd5e1")
    _label(draw, (458, 230), "Nueva carpeta", size=31)
    _rounded(draw, (430, 270, 804, 350), fill=PALE_BLUE, radius=14)
    _label(draw, (458, 310), "↑  Subir archivo", size=33, bold=True, anchor="lm")
    _label(draw, (458, 407), "Subir carpeta", size=31)
    _badge(draw, (812, 273), 1)
    _rounded(draw, (1040, 270, 1450, 594), fill="#fff8db", outline="#d79c00", width=4, radius=28)
    draw.polygon(((1085, 350), (1200, 350), (1234, 385), (1405, 385), (1405, 548), (1085, 548)), fill=YELLOW)
    _label(draw, (1245, 498), "COCID_Curso_Datos", size=27, bold=True, anchor="mm")
    _rounded(draw, (750, 510, 1010, 676), fill="white", outline="#cbd5e1", radius=18)
    _label(draw, (880, 557), "PDF", size=34, color=RED, bold=True, anchor="mm")
    _label(draw, (880, 618), "guia.pdf", size=27, anchor="mm")
    draw.line((1015, 560, 1115, 490), fill=BLUE, width=10)
    draw.polygon(((1115, 490), (1080, 497), (1101, 525)), fill=BLUE)
    _badge(draw, (1008, 615), 2)


def _docs_canvas(draw: ImageDraw.ImageDraw, *, name: str = "Documento sin título") -> None:
    _label(draw, (75, 151), "▣", size=55, color=BLUE, bold=True)
    _rounded(draw, (148, 126, 700, 194), fill="white", outline="#cbd5e1", radius=10)
    _label(draw, (175, 160), name, size=29, anchor="lm")
    _rounded(draw, (1190, 128, 1518, 198), fill=BLUE, radius=24)
    _label(draw, (1354, 163), "Compartir", size=30, color="white", bold=True, anchor="mm")
    _rounded(draw, (210, 300, 1388, 760), fill="white", outline="#d7dee8", radius=4)


def _draw_docs_01(image: Image.Image, draw: ImageDraw.ImageDraw) -> None:
    del image
    _docs_canvas(draw)
    _badge(draw, (690, 129), 1)
    _label(draw, (310, 374), "Título de la minuta", size=42, color="#2f3b52", bold=True)
    _label(draw, (310, 452), "Empieza a escribir aquí", size=31, color="#8a94a6")
    draw.line((309, 500, 309, 566), fill=BLUE, width=5)
    _badge(draw, (354, 540), 2)


def _draw_docs_02(image: Image.Image, draw: ImageDraw.ImageDraw) -> None:
    del image
    _docs_canvas(draw, name="Minuta_COCID")
    _rounded(draw, (110, 222, 1490, 288), fill="white", outline="#cbd5e1", radius=18)
    tools = (("Texto normal", 250), ("Arial", 500), ("B", 700), ("≡", 865), ("• Lista", 1030))
    for label, x in tools:
        _label(draw, (x, 255), label, size=27, bold=label == "B", anchor="mm")
        draw.line((x + 90, 232, x + 90, 277), fill="#d2d9e4", width=2)
    _badge(draw, (1455, 222), 1)
    _label(draw, (320, 375), "Acuerdos", size=43, bold=True)
    for index, text in enumerate(("Revisar materiales", "Comentar avances", "Confirmar la entrega")):
        _label(draw, (345, 454 + index * 68), f"•  {text}", size=31)


def _draw_docs_03(image: Image.Image, draw: ImageDraw.ImageDraw) -> None:
    del image
    _docs_canvas(draw, name="Minuta_COCID")
    _badge(draw, (1500, 132), 1)
    _rounded(draw, (745, 225, 1460, 735), fill="white", outline="#cbd5e1", radius=24)
    _label(draw, (795, 286), "Compartir “Minuta_COCID”", size=35, bold=True)
    _rounded(draw, (795, 335, 1408, 410), fill="white", outline="#cbd5e1", radius=12)
    _label(draw, (825, 373), "persona@ejemplo.invalid", size=26, color=MUTED, anchor="lm")
    _label(draw, (795, 468), "Permiso", size=25, color=MUTED)
    roles = (("Lector", "Solo consulta"), ("Comentador", "Consulta y comentarios"), ("Editor", "Puede modificar"))
    for index, (role, detail) in enumerate(roles):
        y = 520 + index * 62
        if index == 1:
            _rounded(draw, (785, y - 25, 1418, y + 29), fill=PALE_BLUE, radius=12)
        _label(draw, (815, y), role, size=27, bold=index == 1, anchor="lm")
        _label(draw, (1380, y), detail, size=22, color=MUTED, anchor="rm")
    _badge(draw, (1424, 471), 2)


DRAWERS: dict[str, Callable[[Image.Image, ImageDraw.ImageDraw], None]] = {
    "drive_01_nuevo.png": _draw_drive_01,
    "drive_02_crear_carpeta.png": _draw_drive_02,
    "drive_03_subir_archivo.png": _draw_drive_03,
    "docs_01_crear_y_renombrar.png": _draw_docs_01,
    "docs_02_barra_de_herramientas.png": _draw_docs_02,
    "docs_03_compartir_permisos.png": _draw_docs_03,
}


def build_assets(output_dir: str | Path) -> dict[str, Any]:
    """Generate all tutorial PNG files and their accessible logical manifest."""
    output = validate_mutable_path(Path(output_dir))
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    manifest: dict[str, Any] = {"format": "cocid_drive_docs_tutorial_assets_v1", "assets": {}}
    for filename, spec in ASSET_SPECS.items():
        product = "Drive" if filename.startswith("drive_") else "Docs"
        image, draw = _base(spec, product)
        DRAWERS[filename](image, draw)
        destination = validate_mutable_path(output / filename, allowed_root=output)
        image.save(destination, format="PNG", optimize=True)
        manifest["assets"][filename] = {
            **spec,
            "width": CANVAS[0],
            "height": CANVAS[1],
        }
    manifest_path = validate_mutable_path(output / "manifest.json", allowed_root=output)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def parse_args() -> argparse.Namespace:
    """Parse the explicit output directory without creating anything on import."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=get_runtime_dir() / "cocid_drive_docs_tutorial_assets",
    )
    return parser.parse_args()


def main() -> int:
    """Generate the six local illustrations."""
    args = parse_args()
    manifest = build_assets(args.output_dir)
    print(f"Generated {len(manifest['assets'])} tutorial assets in {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
