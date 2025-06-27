import tempfile
import subprocess
import os
from pathlib import Path
import yaml
from schemas.schemas import (
    ConceptoBase, TipoTitulo, TipoReferencia, TipoPresentacion, NivelContexto,
    GradoFormalidad, NivelSimbolico, TipoAplicacion
)

def seleccionar_enum(enum_cls):
    opciones = list(enum_cls)
    for idx, opt in enumerate(opciones, 1):
        print(f" [{idx}] {opt.value}")
    while True:
        try:
            sel = int(input("Seleccione (número): "))
            if 1 <= sel <= len(opciones):
                return opciones[sel - 1]
        except ValueError:
            pass
        print("⚠️ Selección inválida. Intente de nuevo.")

def abrir_editor_vscode(texto_inicial=""):
    with tempfile.NamedTemporaryFile(suffix=".tex", mode="w+", delete=False) as tmp:
        tmp.write(texto_inicial)
        tmp.flush()
        subprocess.run(["code", "--wait", tmp.name])
        tmp.seek(0)
        contenido = tmp.read()
    os.unlink(tmp.name)
    return contenido.strip()

def capturar_booleano(msg, default=False):
    resp = input(f"{msg} [{'Y/n' if default else 'y/N'}]: ").strip().lower()
    if not resp:
        return default
    return resp in ("y", "yes", "s", "si")

def main():
    print("✔️ Crear nuevo concepto matemático\n")

    data = {}
    data["id"] = input("ID (ej. def:grupo_001): ")

    print("Tipo:")
    tipos = ["definicion", "proposicion", "teorema", "corolario", "ejemplo", "lema", "nota"]
    for i, t in enumerate(tipos, 1):
        print(f" [{i}] {t}")
    data["tipo"] = tipos[int(input("Seleccione: ")) - 1]

    data["titulo"] = input("Título (opcional): ") or None
    print("Tipo de título:")
    data["tipo_titulo"] = seleccionar_enum(TipoTitulo)

    data["categorias"] = [c.strip() for c in input("Categorías (separadas por coma): ").split(",") if c.strip()]

    if capturar_booleano("¿Abrir VSCode para capturar contenido LaTeX?", True):
        contenido = abrir_editor_vscode()
        if '---' in contenido:
            print("⚠️ Advertencia: Se detectó '---' dentro del contenido, será eliminado.")
            contenido = contenido.replace('---', '')
        data["contenido_latex"] = contenido
    else:
        data["contenido_latex"] = input("Contenido LaTeX (línea única): ")

    data["es_algoritmo"] = capturar_booleano("¿Es un algoritmo?", False)

    if capturar_booleano("¿Agregar referencia?", False):
        ref = {
            "tipo_referencia": seleccionar_enum(TipoReferencia),
            "autor": input("Autor: ") or None,
            "fuente": input("Fuente: ") or None,
            "anio": int(input("Año: ")) if capturar_booleano("¿Ingresar año?", False) else None,
            "tomo": input("Tomo: ") or None,
            "paginas": input("Páginas: ") or None,
            "capitulo": input("Capítulo: ") or None,
            "seccion": input("Sección: ") or None,
            "editorial": input("Editorial: ") or None,
            "doi": input("DOI: ") or None,
            "url": input("URL: ") or None
        }
        data["referencia"] = ref

    if capturar_booleano("¿Agregar contexto docente?", False):
        data["contexto_docente"] = {
            "nivel_contexto": seleccionar_enum(NivelContexto),
            "grado_formalidad": seleccionar_enum(GradoFormalidad)
        }

    if capturar_booleano("¿Agregar metadatos técnicos?", False):
        raw = input("Conceptos previos (coma separada, opcional): ").strip()
        previos = [p.strip() for p in raw.split(",") if p.strip()]
        meta = {
            "usa_notacion_formal": capturar_booleano("¿Usa notación formal?", True),
            "incluye_demostracion": capturar_booleano("¿Incluye demostración?", False),
            "es_definicion_operativa": capturar_booleano("¿Es definición operativa?", False),
            "es_concepto_fundamental": capturar_booleano("¿Es concepto fundamental?", False),
            "requiere_conceptos_previos": previos or None,
            "incluye_ejemplo": capturar_booleano("¿Incluye ejemplo?", False),
            "es_autocontenible": capturar_booleano("¿Es autocontenible?", True),
            "tipo_presentacion": seleccionar_enum(TipoPresentacion),
            "nivel_simbolico": seleccionar_enum(NivelSimbolico),
            "tipo_aplicacion": [seleccionar_enum(TipoAplicacion)] if capturar_booleano("¿Agregar tipo de aplicación?", False) else None
        }
        data["metadatos_tecnicos"] = meta
        data["alias_previos_pendientes"] = previos or None
    else:
        data["alias_previos_pendientes"] = None

    data["source"] = input("Fuente (carpeta): ")

    concepto = ConceptoBase(**data)

    carpeta = Path(f"data/{concepto.source}")
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / f"{concepto.id.replace(':', '_')}.md"

    # Usar mode="json" para asegurar que enums y fechas se exporten como texto plano
    concepto_dict = concepto.model_dump(mode="json", exclude={"contenido_latex"}, exclude_none=True)

    with open(ruta, "w", encoding="utf-8") as f:
        f.write("---\n")
        yaml.dump(concepto_dict, f, sort_keys=False, allow_unicode=True)
        f.write("---\n\n")
        f.write(concepto.contenido_latex)

    print(f"✔️ Guardado en {ruta}")

if __name__ == "__main__":
    main()
