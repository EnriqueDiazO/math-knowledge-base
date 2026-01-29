"""Facade local de enums usados por el editor.

Este módulo existe para desacoplar editor_streamlit.py
del paquete schemas.schemas durante el refactor.
"""

from schemas.schemas import GradoFormalidad
from schemas.schemas import NivelContexto
from schemas.schemas import NivelSimbolico
from schemas.schemas import TipoAplicacion

__all__ = [
    "GradoFormalidad",
    "NivelContexto",
    "NivelSimbolico",
    "TipoAplicacion",
]


# OJO: mapea a tu Enum TipoReferencia: libro, articulo, tesis, tesina, pagina_web, miscelanea
_TIPO_MAP = {
    "book": "libro",
    "article": "articulo",
    "phdthesis": "tesis",
    "mastersthesis": "tesis",
    "inproceedings": "articulo",   # o "miscelanea" si prefieres
    "incollection": "miscelanea",  # capítulo en libro → miscelanea (si no tienes "capitulo" como tipo)
    "proceedings": "miscelanea",
    "techreport": "miscelanea",
    "misc": "miscelanea",
    "unpublished": "miscelanea",
    "online": "pagina_web",
    "www": "pagina_web",
}