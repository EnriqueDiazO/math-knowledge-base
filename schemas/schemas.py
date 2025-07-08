from __future__ import annotations
from pydantic import BaseModel, Field, ConfigDict
from typing import Literal
from typing import List, Optional
from datetime import datetime
from enum import Enum


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

class TipoReferencia(str, Enum):
    libro = "libro"
    articulo = "articulo"
    tesis = "tesis"
    tesina = "tesina"
    pagina_web = "pagina_web"
    miscelanea = "miscelanea"


# ----------------------------
# ENUMS para tipos de relación
# ----------------------------

class TipoRelacion(str, Enum):
    equivalente = "equivalente"
    deriva_de = "deriva_de"
    inspirado_en = "inspirado_en"
    requiere_concepto = "requiere_concepto"
    implica = "implica"
    contrasta_con = "contrasta_con"
    contradice = "contradice"
    contra_ejemplo = "contra_ejemplo"



# ----------------------------
# SUBMODELOS ESTRUCTURADOS
# ----------------------------

class Referencia(BaseModel):
    """Información bibliográfica del concepto"""
    tipo_referencia: Optional[TipoReferencia] = Field(..., description="Tipo de referencia (libro, articulo, tesis, etc.)")
    autor: Optional[str]
    fuente: Optional[str]
    anio: Optional[int]
    tomo: Optional[str]
    edicion: Optional[str]
    paginas: Optional[str]
    capitulo: Optional[str]
    seccion: Optional[str]
    editorial: Optional[str]
    doi: Optional[str]
    url: Optional[str]
    issbn: Optional[str]

    model_config = ConfigDict(from_attributes=True)

class RelationEnriched(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    relation: Relation
    desde_ref: Optional[Referencia]
    hasta_ref: Optional[Referencia]

class ContextoDocente(BaseModel):
    """Contexto de uso docente del concepto"""
    nivel_contexto: NivelContexto
    grado_formalidad: GradoFormalidad

    model_config = ConfigDict(from_attributes=True)

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

    model_config = ConfigDict(from_attributes=True)


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

    source: str = Field(..., description="Nombre de la carpeta contenedora de los conceptos")
    alias_previos_pendientes: Optional[List[str]] = None

    model_config = ConfigDict(from_attributes=True)


# ----------------------------
# SUBCLASES POR TIPO DE CONCEPTO
# ----------------------------

class Definicion(ConceptoBase):
    tipo: Literal["definicion"] = "definicion"

class Teorema(ConceptoBase):
    tipo: Literal["teorema"] = "teorema"
    demostracion: Optional[dict] = None

class Proposicion(ConceptoBase):
    tipo: Literal["proposicion"] = "proposicion"
    demostracion: Optional[dict] = None

class Corolario(ConceptoBase):
    tipo: Literal["corolario"] = "corolario"
    demostracion: Optional[dict] = None

class Lema(ConceptoBase):
    tipo: Literal["lema"] = "lema"
    demostracion: Optional[dict] = None

class Ejemplo(ConceptoBase):
    tipo: Literal["ejemplo"] = "ejemplo"
    descripcion: Optional[str] = None

class Nota(ConceptoBase):
    tipo: Literal["nota"] = "nota"
    aclaracion: Optional[str] = None



# ----------------------------
# MODELO PRINCIPAL: Relation
# ----------------------------

class Relation(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)
    desde_id: str = Field(..., description="ID del concepto origen")
    desde_source: str = Field(..., description="Fuente del concepto origen")
    hasta_id: str = Field(..., description="ID del concepto destino")
    hasta_source: str = Field(..., description="Fuente del concepto destino")
    tipo: TipoRelacion = Field(..., description="Tipo de relación")
    descripcion: Optional[str] = Field("", description="Descripción opcional de la relación")

# ----------------------------
# MODELO PRINCIPAL: LineageResult
# ----------------------------

class LineageResult(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)
    root: str  # el ID completo del concepto inicial, e.g. "def:anillo_001@BookB"
    path: List[str]  # lista de IDs completos conectados a través del grafo




# ----------------------------
# MODELO PRINCIPAL: DocumentoLaTeX
# ----------------------------


class DocumentoConTimestamp(BaseModel):
    fecha_creacion: datetime = Field(default_factory=datetime.now)
    ultima_actualizacion: datetime = Field(default_factory=datetime.now)
    model_config = ConfigDict(from_attributes=True)

class DocumentoLatex(DocumentoConTimestamp):
    id: str
    source: str
    contenido_latex: str
    model_config = ConfigDict(from_attributes=True)
