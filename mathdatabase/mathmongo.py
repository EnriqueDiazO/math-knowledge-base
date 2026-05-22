from pymongo import MongoClient, ASCENDING
from pathlib import Path
from pydantic import ValidationError
from schemas.schemas import ConceptoBase, Relation, TipoRelacion, RelationEnriched, Referencia, LineageResult
from schemas.schemas import DocumentoLatex
from typing import List, Optional
from parsers.yaml_latex_parser import YamlLatexParser
from datetime import datetime

class MathMongo:
    def __init__(self, mongo_uri="mongodb://localhost:27017", db_name="mathmongo"):
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.concepts = self.db["concepts"]
        self.relations = self.db["relations"]
        self.latex_documents = self.db["latex_documents"]
        print(f"✅ Conectado a la base de datos {db_name}")


        self.concepts.create_index([("id", ASCENDING),
                                     ("source", ASCENDING)],
                                       unique=True)
        self.latex_documents.create_index([("id", ASCENDING),
                                            ("source", ASCENDING)], 
                                            unique=True)
        self.relations.create_index([("desde", ASCENDING),
                                      ("hasta", ASCENDING),
                                        ("tipo", ASCENDING)], unique=True)



    def ingest_folder(self, folder: str, source: str) -> list[ConceptoBase]:
        resultados = []
        path = Path(folder)
        for file_path in path.glob("*.md"):
            print(f"Procesando archivo: {file_path.name}")
            meta, contenido_latex = YamlLatexParser.extraer_yaml_y_contenido(str(file_path))
            meta["source"] = source
            

            try:
                concepto = ConceptoBase(**meta, contenido_latex=contenido_latex)
            except ValidationError as e:
                print(f"❌ Error en {file_path.name}: {e}")
                continue

            concepto_dict = concepto.model_dump(mode="python", exclude={"contenido_latex"}, exclude_none=True)
            
            self.concepts.update_one(
                {"id": concepto.id, "source": source},
                {"$set": concepto_dict},upsert=True)
            
            # 2. Guardar contenido LaTeX en latex_documents
            now = datetime.now()

            self.latex_documents.update_one(
            {"id": concepto.id, "source": source},
            {
                "$set": {
                    "contenido_latex": contenido_latex,
                    "ultima_actualizacion": now
                },
                "$setOnInsert": {"fecha_creacion": now}
            },upsert=True)

            resultados.append(concepto)

        return resultados

    def get_concepts_by_source(self, source: str) -> list[dict]:
        """Return concept metadata documents for a source."""
        return list(self.concepts.find({"source": source}))

    def get_latex_document(self, concept_id: str, source: str) -> Optional[dict]:
        """Return the LaTeX document associated with a concept."""
        return self.latex_documents.find_one({"id": concept_id, "source": source})

    def get_concepts_with_latex_by_source(self, source: str) -> list[dict]:
        """Return concept metadata enriched with contenido_latex from latex_documents."""
        enriched = []
        for concept in self.get_concepts_by_source(source):
            doc = dict(concept)
            latex_doc = self.get_latex_document(doc.get("id"), source) or {}
            doc["contenido_latex"] = latex_doc.get("contenido_latex", "")
            enriched.append(doc)
        return enriched

    def get_relations_by_source(self, source: str) -> list[dict]:
        """Return relations where either endpoint belongs to source."""
        return list(
            self.relations.find(
                {
                    "$or": [
                        {"desde": {"$regex": f"@{source}$"}},
                        {"hasta": {"$regex": f"@{source}$"}},
                    ]
                }
            )
        )

    def update_latex_document(self, concept_id: str, source: str, new_latex: str) -> None:
        """Explicitly update LaTeX content for a concept.

        This method is intentionally not used automatically by validators.
        Call it only after the user has confirmed they want to write changes.
        """
        self.latex_documents.update_one(
            {"id": concept_id, "source": source},
            {
                "$set": {
                    "contenido_latex": new_latex,
                    "ultima_actualizacion": datetime.now(),
                }
            },
            upsert=False,
        )

    def get_notebook_notes(self, query: Optional[dict] = None, limit: int = 100) -> list[dict]:
        """Return latex diary notes from the experimental Cuaderno module."""
        return list(
            self.db["latex_notes"]
            .find(query or {})
            .sort([("date", -1), ("updated_at", -1)])
            .limit(int(limit))
        )

    def get_notebook_note_by_id(self, note_id) -> Optional[dict]:
        from bson import ObjectId

        try:
            doc = self.db["latex_notes"].find_one({"_id": ObjectId(str(note_id))})
            if doc is not None:
                return doc
        except Exception:
            pass
        return self.db["latex_notes"].find_one({"_id": str(note_id)})

    def create_notebook_note(self, note_data: dict):
        now = datetime.now()
        doc = dict(note_data)
        doc.setdefault("created_at", now)
        doc.setdefault("updated_at", now)
        return self.db["latex_notes"].insert_one(doc)

    def update_notebook_note(self, note_id, note_data: dict):
        from bson import ObjectId

        update = dict(note_data)
        update["updated_at"] = datetime.now()
        try:
            res = self.db["latex_notes"].update_one({"_id": ObjectId(str(note_id))}, {"$set": update})
            if getattr(res, "matched_count", 0) > 0:
                return res
        except Exception:
            pass
        return self.db["latex_notes"].update_one({"_id": str(note_id)}, {"$set": update})

    def delete_notebook_note(self, note_id):
        from bson import ObjectId

        try:
            res = self.db["latex_notes"].delete_one({"_id": ObjectId(str(note_id))})
            if getattr(res, "deleted_count", 0) > 0:
                return res
        except Exception:
            pass
        return self.db["latex_notes"].delete_one({"_id": str(note_id)})

    def get_notebook_projects(self) -> list[str]:
        projects = {}
        for project in self.db["latex_notes"].distinct("project"):
            if not isinstance(project, str):
                continue
            clean = " ".join(project.split())
            if clean:
                projects.setdefault(clean.lower(), clean)
        return sorted(projects.values(), key=str.lower)

    def get_notes_by_project(self, project_name: str) -> list[dict]:
        clean = " ".join((project_name or "").split())
        if not clean:
            query = {"$or": [{"project": ""}, {"project": None}, {"project": {"$exists": False}}]}
        else:
            query = {"project": clean}
        return self.get_notebook_notes(query=query, limit=500)

    def get_project_note_counts(self) -> list[dict]:
        pipeline = [
            {
                "$project": {
                    "project": {
                        "$cond": [
                            {"$or": [{"$eq": ["$project", ""]}, {"$eq": ["$project", None]}]},
                            "Sin proyecto",
                            "$project",
                        ]
                    },
                    "updated_at": 1,
                    "context": 1,
                    "tags": 1,
                }
            },
            {
                "$group": {
                    "_id": "$project",
                    "count": {"$sum": 1},
                    "last_updated": {"$max": "$updated_at"},
                    "contexts": {"$addToSet": "$context"},
                    "tags": {"$push": "$tags"},
                }
            },
            {"$sort": {"count": -1, "_id": 1}},
        ]
        return [
            {
                "project": item.get("_id") or "Sin proyecto",
                "count": item.get("count", 0),
                "last_updated": item.get("last_updated"),
                "contexts": item.get("contexts", []),
                "tags": item.get("tags", []),
            }
            for item in self.db["latex_notes"].aggregate(pipeline)
        ]

    def get_notebook_contexts(self) -> list[str]:
        return sorted(
            {
                c
                for c in self.db["latex_notes"].distinct("context")
                if isinstance(c, str) and c.strip()
            },
            key=str.lower,
        )

    def get_notebook_tags(self) -> list[str]:
        return sorted(
            {
                tag
                for tag in self.db["latex_notes"].distinct("tags")
                if isinstance(tag, str) and tag.strip()
            },
            key=str.lower,
        )

    def get_notebook_dates_summary(self) -> list[dict]:
        pipeline = [
            {"$group": {"_id": "$date", "count": {"$sum": 1}}},
            {"$sort": {"_id": -1}},
        ]
        return [{"date": item.get("_id"), "count": item.get("count", 0)} for item in self.db["latex_notes"].aggregate(pipeline)]

    def get_notebook_notes_by_date(self, date_str: str) -> list[dict]:
        return self.get_notebook_notes(query={"date": date_str}, limit=500)

    def get_notebook_notes_by_month(self, year: int, month: int) -> list[dict]:
        prefix = f"{int(year):04d}-{int(month):02d}-"
        return self.get_notebook_notes(query={"date": {"$regex": f"^{prefix}"}}, limit=1000)
    
    def add_relation(
            self,
            desde_id: str,
            desde_source: str,
            hasta_id: str,
            hasta_source: str,
            tipo: str,
            descripcion: str = "",
            validar_existencia: bool = True) -> Optional[Relation]:
        """
        Crea o actualiza una relación semántica entre dos conceptos.

        :param desde_id: ID del concepto origen (por ej. "def:grupo_001")
        :param desde_source: fuente del concepto origen (por ej. "LibroA")
        :param hasta_id: ID del concepto destino (por ej. "def:grupo_001")
        :param hasta_source: fuente del concepto destino (por ej. "LibroB")
        :param tipo: tipo de relación (ej. "equivalente", "deriva_de", "inspirado_en", etc.)
        :param descripcion: texto opcional que detalla la relación
        :param validar_existencia: Si es True, verifica que ambos conceptos existan antes de crear la relación
        """

        if validar_existencia:
            origen = self.concepts.find_one({"id": desde_id, "source": desde_source})
            destino = self.concepts.find_one({"id": hasta_id, "source": hasta_source})
            if not origen or not destino:
                print("⚠️ No se puede crear la relación: uno o ambos conceptos no existen.")
                return None
        
        rel = Relation(
            desde_id=desde_id,
            desde_source=desde_source,
            hasta_id=hasta_id,
            hasta_source=hasta_source,
            tipo=tipo,
            descripcion=descripcion
        )
        
        doc = {
            "desde": f"{rel.desde_id}@{rel.desde_source}",
            "hasta": f"{rel.hasta_id}@{rel.hasta_source}",
            "tipo": rel.tipo,
            "descripcion": rel.descripcion
        }

        self.relations.update_one(
            {"desde": doc["desde"], "hasta": doc["hasta"], "tipo": doc["tipo"]},
            {"$set": doc},
            upsert=True
        )
        print(f"🔗 Relación registrada: {doc['desde']} --[{doc['tipo']}]--> {doc['hasta']}")
        return rel
    

 
    def get_relations(
            self,
            desde_id: Optional[str] = None,
            desde_source: Optional[str] = None,
            hasta_id: Optional[str] = None,
            hasta_source: Optional[str] = None,
            tipo: Optional[TipoRelacion] = None) -> List[Relation]:
        """Obtiene las relaciones según filtros opcionales.
        - desde_id + desde_source
        - hasta_id + hasta_source
        - tipo (enum).
        """  # noqa: D205
        query = {}
        if desde_id and desde_source:
            query["desde"] = f"{desde_id}@{desde_source}"
        if hasta_id and hasta_source:
            query["hasta"] = f"{hasta_id}@{hasta_source}"
        if tipo:
            query["tipo"] = tipo.value

        docs = self.relations.find(query)
        relaciones = []
        for d in docs:
            rel = Relation(
            desde_id=d["desde"].split("@")[0],
            desde_source=d["desde"].split("@")[1],
            hasta_id=d["hasta"].split("@")[0],
            hasta_source=d["hasta"].split("@")[1],
            tipo=d["tipo"],  # con enum string
            descripcion=d.get("descripcion", ""))
            relaciones.append(rel)
        return relaciones
    

    def get_relations_with_references(
        self,
        desde_id: Optional[str] = None,
        desde_source: Optional[str] = None,
        hasta_id: Optional[str] = None,
        hasta_source: Optional[str] = None,
        tipo: Optional[TipoRelacion] = None) -> List[RelationEnriched]:
        """
        Obtiene relaciones y las enriquece con referencias bibliográficas si existen.
        """
        relaciones = self.get_relations(
        desde_id=desde_id,
        desde_source=desde_source,
        hasta_id=hasta_id,
        hasta_source=hasta_source,
        tipo=tipo)

        resultados = []
        for r in relaciones:
             doc_desde = self.concepts.find_one({"id": r.desde_id, "source": r.desde_source})
             doc_hasta = self.concepts.find_one({"id": r.hasta_id, "source": r.hasta_source})

             ref_desde = doc_desde.get("referencia") if doc_desde else None
             ref_hasta = doc_hasta.get("referencia") if doc_hasta else None
             enriched = RelationEnriched(
            relation=r,
            desde_ref=(Referencia.model_validate(ref_desde)
                       if isinstance(ref_desde, dict) and ref_desde.get("tipo_referencia")
                       else None),
            hasta_ref=(Referencia.model_validate(ref_hasta)
                       if isinstance(ref_hasta, dict) and ref_hasta.get("tipo_referencia")
                       else None))
             resultados.append(enriched)


        return resultados

    def get_lineage(
            self,
            full_id: str,
            direction: str = "up",
            rel_types: Optional[list[TipoRelacion]] = None,
            max_depth: int = 3
            ) -> LineageResult:
        """Obtiene el árbol de dependencias o derivaciones de un concepto.

        :param full_id: ID completo del concepto en formato "id@source"
        :param direction: "up" para buscar conceptos de los que depende, "down" para descendientes
        :param rel_types: Lista de tipos de relación a considerar
        :param max_depth: Profundidad máxima de búsqueda
        """
        if not rel_types:
            rel_types = [TipoRelacion.implica,TipoRelacion.deriva_de, TipoRelacion.requiere_concepto]

        from_field = "hasta" if direction == "up" else "desde"
        to_field = "desde" if direction == "up" else "hasta"

        pipeline = [
            {"$match": {from_field: full_id, "tipo": {"$in": [t.value for t in rel_types]}}},
            {"$graphLookup": {
            "from": "relations",
            "startWith": f"${to_field}",
            "connectFromField": to_field,
            "connectToField": from_field,
            "as": "lineage",
            "maxDepth": max_depth - 1,
            "restrictSearchWithMatch": {"tipo": {"$in": [t.value for t in rel_types]}}}},
            {"$project": {to_field: 1, "lineage." + to_field: 1}}
        ]

        ids = set([full_id])
        for doc in self.relations.aggregate(pipeline):
            ids.add(doc.get(to_field))
            for node in doc.get("lineage", []):
                ids.add(node.get(to_field))

        return LineageResult(root=full_id, path=list(ids))

        
