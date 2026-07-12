#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import shutil
from pathlib import Path
from typing import Dict
from typing import List

from pymongo import MongoClient

from editor.utils.media_assets import copy_media_tree_for_latex
from exporters_latex.latex_compile import latex_failure_message
from exporters_latex.latex_compile import latex_warning_message
from exporters_latex.latex_compile import run_latex_until_stable
from exporters_latex.unified_document import export_unified_document_with_inputs
from exporters_latex.unified_document import render_concept_fragment
from mathkb_config import LATEX_MAX_PASSES
from mathkb_config import PDF_COMPILE_TIMEOUT_SECONDS
from mathmongo.config import resolve_config
from mathmongo.paths import get_exports_dir
from mathmongo.paths import resolve_home_path
from mathmongo.paths import validate_mutable_path


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
        salida: str | None = None,
    ) -> None:
        """Genera `.tex` y `.pdf` para un único concepto."""

        if salida is None:
            output_path = get_exports_dir(
                configured=resolve_config().export_directory
            ) / "concepts"
        else:
            output_path = resolve_home_path(salida)
        salida = str(validate_mutable_path(output_path))

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
        copy_media_tree_for_latex(salida)

        # ---------- Creamos fichero .tex ----------
        tex_path = os.path.join(salida, f"{nombre_base}.tex")
        self._escribir_tex(tex_path, concepto, contenido_latex)

        # ---------- Compilamos ----------
        command = [
            "pdflatex",
            "-interaction=nonstopmode",
            Path(tex_path).name,
        ]
        try:
            pdf_path = Path(salida) / f"{nombre_base}.pdf"
            compile_info = run_latex_until_stable(
                command,
                cwd=Path(salida),
                tex_file=Path(tex_path).name,
                pdf_path=pdf_path,
                log_path=Path(salida) / f"{nombre_base}.log",
                timeout_seconds=PDF_COMPILE_TIMEOUT_SECONDS,
                max_passes=LATEX_MAX_PASSES,
            )
            if compile_info["status"] == "failed":
                result = compile_info.get("result")
                raise RuntimeError(
                    latex_failure_message(
                        tex_path,
                        command,
                        compile_info.get("returncode"),
                        log_excerpt=compile_info.get("log_excerpt", ""),
                        stdout=getattr(result, "stdout", "") if result else "",
                        stderr=getattr(result, "stderr", "") if result else "",
                    )
                )
            if compile_info["status"] == "success_with_warnings":
                print(latex_warning_message(compile_info))
            print(f"📄 PDF generado: {pdf_path}")
        except (TimeoutError, FileNotFoundError, PermissionError, OSError, RuntimeError) as err:
            print(f"❌ Error al compilar LaTeX: {err}")
            raise

    def exportar_todos_de_source(
        self,
        db: MongoClient,
        source: str,
        salida: str | None = None,
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
        salida: str | None = None,
        titulo: str | None = None,
        agrupar_por_tipo: bool = False,
        respetar_orden_manual: bool = True,
        compilar_pdf: bool = True,
        sobrescribir: bool = False,
    ):
        """Exporta un documento maestro modular con fragments incluidos via \\input."""
        if salida is None:
            output_path = get_exports_dir(
                configured=resolve_config().export_directory
            ) / "documents"
        else:
            output_path = resolve_home_path(salida)
        return export_unified_document_with_inputs(
            source=source,
            concepts=conceptos,
            output_dir=validate_mutable_path(output_path),
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
            f.write(r"\usepackage{graphicx}" "\n")
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
