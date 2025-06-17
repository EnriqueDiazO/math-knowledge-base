from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from enum import Enum
from __future__ import annotations

# ----------------------------
# ENUMS para campos categóricos
# ----------------------------

class TipoTitulo(str, Enum):
    canonico = "canonico"
    descripcion = "descripcion"
    generado = "generado"
    ninguno = "ninguno"

class TipoPresentacion(str, Enum):
    expositivo = "expositivo"
    axiomatico = "axiomatico"
    constructivo = "constructivo"
    contrapositivo = "contrapositivo"
    visual = "visual"

class NivelContexto(str, Enum):
    introductorio = "introductorio"
    intermedio = "intermedio"
    avanzado = "avanzado"
    investigacion = "investigacion"

class GradoFormalidad(str, Enum):
    informal = "informal"
    semi_formal = "semi-formal"
    formal = "formal"
    clasico_formal = "clasico-formal"

class NivelSimbolico(str, Enum):
    bajo = "bajo"
    moderado = "moderado"
    alto = "alto"

class TipoAplicacion(str, Enum):
    teorico = "teorico"
    didactico = "didactico"
    algoritmico = "algoritmico"
    modelado = "modelado"
    historico = "historico"


# ----------------------------
# SUBMODELOS ESTRUCTURADOS
# ----------------------------

class Referencia(BaseModel):
    """Información bibliográfica del concepto"""
    autor: Optional[str]
    fuente: Optional[str]
    anio: Optional[int]
    tomo: Optional[str]
    paginas: Optional[str]
    capitulo: Optional[str]
    seccion: Optional[str]
    editorial: Optional[str]
    doi: Optional[str]
    url: Optional[str]

    class Config:
        orm_mode = True


class ContextoDocente(BaseModel):
    """Contexto de uso docente del concepto"""
    nivel_contexto: NivelContexto
    grado_formalidad: GradoFormalidad

    class Config:
        orm_mode = True

class MetadatosTecnicos(BaseModel):
    """Metadatos formales y técnicos del contenido"""
    usa_notacion_formal: bool = True
    incluye_demostracion: bool = False
    es_definicion_operativa: bool = False
    es_concepto_fundamental: bool = False
    requiere_conceptos_previos: Optional[List[str]] = None
    incluye_ejemplo: bool = False
    es_autocontenible: bool = True
    tipo_presentacion: TipoPresentacion
    nivel_simbolico: NivelSimbolico
    tipo_aplicacion: Optional[List[TipoAplicacion]] = None

    class Config:
        orm_mode = True


# ----------------------------
# MODELO PRINCIPAL: ConceptoBase
# ----------------------------

class ConceptoBase(BaseModel):
    """
    Modelo general para conceptos matemáticos: definiciones, teoremas, ejemplos, etc.
    """
    id: str
    tipo: Literal["definicion", "proposicion", "teorema", "corolario", "ejemplo", "lema", "nota"]

    titulo: Optional[str] = Field(None, description="Título o encabezado del concepto, si existe")
    tipo_titulo: TipoTitulo = Field(default="ninguno", description="Tipo de título: canonico, descripcion, generado, ninguno")

    contenido_latex: str = Field(..., description="Contenido LaTeX multilínea permitido (usar '|' en YAML)")
    categorias: List[str]

    es_algoritmo: Optional[bool] = Field(default=False, description="Indica si el concepto describe un algoritmo paso a paso")
    pasos_algoritmo: Optional[List[str]] = Field(default=None, description="Lista ordenada de pasos si el concepto es un algoritmo")

    comentario: Optional[str] = None
    referencia: Optional[Referencia] = None
    contexto_docente: Optional[ContextoDocente] = None
    metadatos_tecnicos: Optional[MetadatosTecnicos] = None

    fecha_creacion: Optional[datetime] = Field(default_factory=datetime.now)
    ultima_actualizacion: Optional[datetime] = Field(default_factory=datetime.now)

    class Config:
        orm_mode = True