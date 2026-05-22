#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import shutil
import subprocess
from typing import List, Dict
from pymongo import MongoClient
from pathlib import Path
from exporters_latex.unified_document import export_unified_document_with_inputs
from exporters_latex.unified_document import render_concept_fragment

class ExportadorLatex:
    """
    Exporta conceptos almacenados en MongoDB a documentos LaTeX-PDF,
    copiando las plantillas .sty necesarias en la carpeta destino.
    """

    # ------------------------------------------------------------------
    # 1) ρ C O N F I G U R A C I Ó N
    # ------------------------------------------------------------------
    #: nombres de ficheros .sty que siempre debemos copiar
    _ARCHIVOS_PLANTILLA = ("miestilo.sty", "coloredtheorem.sty")

    def __init__(
        self,
        templates_dir: str = Path(__file__).resolve().parent.parent / "templates_latex",
    ) -> None:
        self.templates_dir = templates_dir
        print("✅ ExportadorLatex listo para conceptos y LaTeX")

    # ------------------------------------------------------------------
    # 2) ρ M É T O D O S   P Ú B L I C O S
    # ------------------------------------------------------------------
    def exportar_concepto(
        self,
        concepto: Dict,
        contenido_latex: str,
        salida: str = "./exportados",
    ) -> None:
        """Genera `.tex` y `.pdf` para un único concepto."""

        # ---------- Validaciones básicas ----------
        if not concepto or not contenido_latex:
            print("❌ Datos incompletos para exportar.")
            return

        # ---------- Normalizamos nombre de archivo ----------
        titulo = concepto.get("titulo", "concepto_sin_titulo")
        titulo_limpio = "".join(
            c if c.isalnum() or c in " _-" else "_" for c in titulo
        ).strip().replace(" ", "_")
        nombre_base = titulo_limpio or "concepto_sin_nombre"

        # ---------- Preparamos carpeta ----------
        os.makedirs(salida, exist_ok=True)
        self._copiar_plantillas(salida)          # ⬅️  nuevo paso

        # ---------- Creamos fichero .tex ----------
        tex_path = os.path.join(salida, f"{nombre_base}.tex")
        self._escribir_tex(tex_path, concepto, contenido_latex)

        # ---------- Compilamos ----------
        try:
            subprocess.run(
                ["pdflatex", "-interaction=nonstopmode",
                 "-output-directory", salida, tex_path],
                check=True,
            )
            print(f"📄 PDF generado: {os.path.join(salida, nombre_base)}.pdf")
        except subprocess.CalledProcessError as err:
            print(f"❌ Error al compilar LaTeX: {err}")

    def exportar_todos_de_source(
        self,
        db: MongoClient,
        source: str,
        salida: str = "./exportados",
    ) -> None:
        """Exporta todos los conceptos provenientes de un mismo *source*."""
        conceptos = list(db.concepts.find({"source": source}))
        print(f"🔎 Conceptos encontrados para '{source}': {len(conceptos)}")

        for c in conceptos:
            doc = db.latex_documents.find_one({"id": c["id"], "source": source})
            if not doc:
                print(f"⚠️  LaTeX no encontrado para {c['id']}")
                continue
            self.exportar_concepto(c, doc.get("contenido_latex", ""), salida)

    def renderizar_fragmento_concepto(
        self,
        concepto: Dict,
        contenido_latex: str,
    ) -> str:
        """Genera un fragmento LaTeX parcial, sin preambulo ni document."""
        return render_concept_fragment(concepto, contenido_latex)

    def exportar_documento_unificado(
        self,
        source: str,
        conceptos: List[Dict],
        salida: str = "./exported",
        titulo: str | None = None,
        agrupar_por_tipo: bool = False,
        respetar_orden_manual: bool = True,
        compilar_pdf: bool = True,
        sobrescribir: bool = False,
    ):
        """Exporta un documento maestro modular con fragments incluidos via \\input."""
        return export_unified_document_with_inputs(
            source=source,
            concepts=conceptos,
            output_dir=salida,
            title=titulo or source,
            agrupar_por_tipo=agrupar_por_tipo,
            respetar_orden_manual=respetar_orden_manual,
            compile_pdf=compilar_pdf,
            overwrite=sobrescribir,
            templates_dir=self.templates_dir,
        )

    # ------------------------------------------------------------------
    # 3) ρ M É T O D O S   P R I V A D O S
    # ------------------------------------------------------------------
    def _copiar_plantillas(self, destino: str) -> None:
        """
        Copia los archivos .sty listados en `_ARCHIVOS_PLANTILLA` desde
        `self.templates_dir` a la carpeta `destino` (si aún no existen).
        """
        for fname in self._ARCHIVOS_PLANTILLA:
            src = os.path.join(self.templates_dir, fname)
            dst = os.path.join(destino, fname)
            if not os.path.exists(src):
                print(f"⚠️  Plantilla no encontrada: {src}")
                continue
            if not os.path.exists(dst):
                shutil.copy2(src, dst)
                print(f"📄 Plantilla {fname} copiada a {destino}")

    @staticmethod
    def _escribir_tex(
        tex_path: str, concepto: Dict, contenido_latex: str
    ) -> None:
        """Escribe el archivo .tex completo con su preámbulo y contenido."""
        with open(tex_path, "w", encoding="utf-8") as f:
            # --- preámbulo mínimo ---
            f.write(r"\documentclass[12pt]{article}" "\n")
            f.write(r"\usepackage{miestilo}" "\n")
            f.write(r"\usepackage{coloredtheorem}" "\n")  # por si acaso
            f.write(r"\begin{document}" "\n\n")

            # --- título ---
            f.write(r"\section*{" + concepto.get("titulo", "Sin título") + "}\n\n")

            # --- cuerpo principal ---
            f.write(contenido_latex + "\n\n")

            # --- comentario opcional ---
            if concepto.get("comentario"):
                f.write(r"\section*{Comentario}" "\n" + concepto["comentario"] + "\n\n")

            # --- referencia bibliográfica opcional ---
            if ref := concepto.get("referencia"):
                f.write(r"\section*{Referencia}" "\n")
                linea1 = ", ".join(
                    filter(None, (
                        ref.get("autor"),
                        ref.get("fuente"),
                        f"({ref.get('anio')})" if ref.get("anio") else None,
                    ))
                )
                f.write(linea1 + r"\\" "\n")

                linea2 = ", ".join(
                    filter(None, (
                        f"Tomo {ref['tomo']}"       if ref.get("tomo") else None,
                        f"Ed. {ref['edicion']}"    if ref.get("edicion") else None,
                        f"Cap. {ref['capitulo']}"  if ref.get("capitulo") else None,
                        f"Sección {ref['seccion']}"if ref.get("seccion") else None,
                        f"Pág. {ref['paginas']}"   if ref.get("paginas") else None,
                        ref.get("editorial"),
                    ))
                )
                if linea2:
                    f.write(linea2 + r"\\" "\n")
                if ref.get("issbn"):
                    f.write(f"ISSBN: {ref['issbn']}\\\\\n")
                if ref.get("doi"):
                    f.write(f"DOI: {ref['doi']}\\\\\n")
                if ref.get("url"):
                    f.write(r"\url{" + ref["url"] + "}\\\\" "\n")
                f.write("\n")

            # --- ID interno ---
            f.write(r"\textbf{ID del concepto:}~\verb|" +
                    f"{concepto.get('id')}@{concepto.get('source')}|" + "\n\n")

            f.write(r"\end{document}" "\n")
