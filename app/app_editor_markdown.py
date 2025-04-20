import streamlit as st
import json
import os

st.title("🧠 Editor de Objetos Matemáticos")

if "obj" not in st.session_state:
    st.session_state.obj = {}

obj = st.session_state.obj

# Inicialización segura
obj.setdefault("titulo", "")
obj.setdefault("tipo", "")
obj.setdefault("contenido_latex", "")
obj.setdefault("demostracion", {"pasos": []})
obj.setdefault("ejemplos_rapidos", [])
obj.setdefault("caso", "")
obj.setdefault("explicacion", "")
obj.setdefault("descripcion", "")
obj.setdefault("imagen", "")
obj.setdefault("referencia", {})
obj.setdefault("categoria", [])
obj.setdefault("tags", [])
obj.setdefault("bibtex_entry", "")
obj.setdefault("condiciones_formales", [])
obj.setdefault("enlaces_salida", [])
obj.setdefault("enlaces_entrada", [])
obj.setdefault("comentario_personal", "")
obj.setdefault("inspirado_en", [])
obj.setdefault("creado_a_partir_de", "")

# --- Campos básicos ---
obj["titulo"] = st.text_input("📌 Título", value=obj["titulo"])
obj["tipo"] = st.selectbox("📂 Tipo", ["definicion", "teorema", "proposicion", "corolario", "lema", "ejemplo", "esquema", "otro"], index=0)
obj["contenido_latex"] = st.text_area("✍️ Contenido LaTeX", height=150, value=obj["contenido_latex"])

# --- Según tipo ---
if obj["tipo"] in ["teorema", "proposicion", "lema", "corolario"]:
    st.subheader("📐 Demostración")
    pasos = []
    n = st.number_input("¿Cuántos pasos?", min_value=1, value=len(obj["demostracion"]["pasos"]) or 1)
    for i in range(n):
        col1, col2 = st.columns([2, 1])
        with col1:
            desc = st.text_area(f"Paso {i+1}", key=f"desc_{i}")
        with col2:
            refs = st.text_input(f"Referencias paso {i+1} (coma)", key=f"refs_{i}")
        pasos.append({"descripcion": desc, "referencias": [r.strip() for r in refs.split(",") if r.strip()]})
    obj["demostracion"]["pasos"] = pasos

if obj["tipo"] == "definicion":
    st.subheader("📎 Ejemplos Rápidos")
    raw = st.text_area("Ejemplos: descripción::latex", value="\n".join(f"{ej['descripcion']}::{ej['latex']}" for ej in obj["ejemplos_rapidos"]))
    obj["ejemplos_rapidos"] = []
    for linea in raw.splitlines():
        if "::" in linea:
            d, l = linea.split("::", 1)
            obj["ejemplos_rapidos"].append({"descripcion": d.strip(), "latex": l.strip()})
    
    obj["condiciones_formales"] = st.text_area("📏 Condiciones formales (una por línea)", value="\n".join(obj["condiciones_formales"])).splitlines()

if obj["tipo"] == "ejemplo":
    obj["caso"] = st.text_input("🎲 Caso ilustrado", value=obj["caso"])
    obj["explicacion"] = st.text_area("🗨️ Explicación", value=obj["explicacion"])

if obj["tipo"] == "esquema":
    obj["descripcion"] = st.text_input("🖼️ Descripción", value=obj["descripcion"])
    obj["imagen"] = st.text_input("🖼️ Imagen (nombre de archivo)", value=obj["imagen"])

# --- Metadatos comunes ---
obj["categoria"] = st.text_input("🏷️ Categorías (coma)", value=", ".join(obj["categoria"])).split(",")
obj["tags"] = st.text_input("🔖 Tags (coma)", value=", ".join(obj["tags"])).split(",")

obj["referencia"]["autor"] = st.text_input("👤 Autor", value=obj["referencia"].get("autor", ""))
obj["referencia"]["año"] = st.text_input("📅 Año", value=obj["referencia"].get("año", ""))
obj["referencia"]["obra"] = st.text_input("📘 Obra", value=obj["referencia"].get("obra", ""))
obj["referencia"]["capitulo"] = st.text_input("📄 Capítulo", value=obj["referencia"].get("capitulo", ""))
obj["referencia"]["página"] = st.text_input("📄 Página", value=obj["referencia"].get("página", ""))
obj["referencia"]["bibkey"] = st.text_input("🔑 BibTeX Key", value=obj["referencia"].get("bibkey", ""))
obj["bibtex_entry"] = st.text_area("📚 Entrada BibTeX", value=obj["bibtex_entry"])

obj["enlaces_salida"] = st.text_input("🔗 Enlaces de salida (coma)", value=", ".join(obj["enlaces_salida"])).split(",")
obj["enlaces_entrada"] = st.text_input("🔗 Enlaces de entrada (coma)", value=", ".join(obj["enlaces_entrada"])).split(",")
obj["inspirado_en"] = st.text_input("💡 Inspirado en (coma)", value=", ".join(obj["inspirado_en"])).split(",")
obj["creado_a_partir_de"] = st.text_input("🧾 Creado a partir de", value=obj["creado_a_partir_de"])
obj["comentario_personal"] = st.text_area("✍️ Comentario personal", value=obj["comentario_personal"])

# --- Previsualización y guardado ---
st.subheader("📄 Vista previa JSON")
st.json(obj)

nombre_archivo = st.text_input("💾 Nombre del archivo", value="nuevo_objeto.json")
if st.button("Guardar JSON"):
    os.makedirs("plantillas", exist_ok=True)
    with open(os.path.join("plantillas", nombre_archivo), "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
    st.success(f"✅ Guardado como {nombre_archivo}")

