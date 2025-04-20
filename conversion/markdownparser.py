import re
import json
import os
import hashlib

class MarkdownParser:
    """
    → Clase para convertir archivos Markdown estructurados en objetos JSON.
    Admite campos teóricos y de ejemplos con estilo Zettelkasten.
    """

    def __init__(self, carpeta_salida: str = "./plantillas") -> None:
        self.carpeta_salida = carpeta_salida

    def parsear_md(self, md_path: str, guardar: bool = True) -> dict:
        with open(md_path, encoding="utf-8") as f:
            contenido = f.read()

        obj = {
            "id": "",
            "tipo": "",
            "titulo": "",
            "contenido_latex": "",
            "comentario": "",
            "comentario_previo": "",
            "demostracion": {"pasos": []},
            "categoria": [],
            "tags": [],
            "referencia": {},
            "bibtex_entry": "",
            "relacionado_con": [],
            "enlaces_salida": [],
            "enlaces_entrada": [],
            "comentario_personal": "",
            "inspirado_en": [],
            "creado_a_partir_de": "",
            "caso": "",
            "explicacion": "",
            "explicacion_latex": "",
            "contexto": ""
        }

        titulo = re.search(r"#\s+(.*?)\n", contenido)
        
        #id_match = re.search(r"\*\*ID\*\*:\s*(.*)", contenido)
        #if id_match:
        #    obj["id"] = id_match.group(1).strip()

        if titulo and not obj["id"]:
            partes = re.findall(r"(proposición|teorema|definición|lema|corolario|ejemplo)\s+(\d+)[\.-]?(\d+)?", titulo.group(1).lower())
            #if partes:
            #    tipo, a, b = partes[0]
            #    obj["tipo"] = tipo.lower()
            tipo_exp = re.search(r"\*\*Tipo\*\*:\s*(\w+)", contenido, re.IGNORECASE)
            if tipo_exp:
                obj["tipo"] = tipo_exp.group(1).strip().lower()
                
            tipo_detectado = obj["tipo"] or "obj"
            slug = re.sub(r"[^\w]+", "-", obj["titulo"].lower()).strip("-")
            resumen = obj["contenido_latex"] or contenido
            hash_val = hashlib.sha1(resumen.encode("utf-8")).hexdigest()[:8]
            obj["id"] = f"{tipo_detectado}:{slug}:{hash_val}"
            obj["titulo"] = titulo.group(1).strip()
            #if partes and not obj["id"]:
            #tipo, a, b = partes[0]
            #prefijo = {
            #        "proposición": "pro",
            #        "teorema": "teo",
            #        "definición": "def",
            #        "lema": "lem",
            #        "corolario": "cor",
            #        "ejemplo": "ej"
            #    }.get(tipo, "obj")
            #obj["id"] = f"{prefijo}_{int(a):02d}{int(b or 0):02d}"

        campos_str_lista = {
            "tipo": "tipo",
            "comentario": "comentario",
            "comentario previo": "comentario_previo",
            "categorías": "categoria",
            "tags": "tags",
            "relacionado con": "relacionado_con",
            "enlaces de salida": "enlaces_salida",
            "enlaces de entrada": "enlaces_entrada",
            "inspirado en": "inspirado_en"
        }

        for campo_md, campo_json in campos_str_lista.items():
            match = re.search(rf"\*\*{campo_md}\*\*:\s*(.*)", contenido, re.IGNORECASE)
            if match:
                obj[campo_json] = [x.strip() for x in match.group(1).split(",")]

        for clave in ["caso", "explicacion", "contexto"]:
            match = re.search(rf"\*\*{clave}\*\*:\s*(.*)", contenido, re.IGNORECASE)
            if match:
                obj[clave] = match.group(1).strip()

        explicacion_latex = re.findall(r"\$\$\s*%%\s*Explicación\s*\$\$(.*?)\$\$", contenido, flags=re.DOTALL)
        if explicacion_latex:
            obj["explicacion_latex"] = explicacion_latex[0].strip()

        ref = re.search(r"\*\*Referencia\*\*:\s*(.*?)\n", contenido)
        if ref:
            partes = [x.strip() for x in ref.group(1).split(",")]
            if len(partes) >= 3:
                obj["referencia"] = {
                    "autor": partes[0],
                    "año": int(partes[1]),
                    "obra": partes[2],
                    "capitulo": partes[3],
                    "pagina": partes[4],
                    "bibkey":partes[5]
                }
            #if len(partes) >= 5:
            #    obj["referencia"].update({
            #        "capitulo": partes[3].replace("Cap.", "").strip(),
            #        "página": partes[4].replace("Pág.", "").strip()
            #    })

        bib = re.search(r"```bibtex(.*?)```", contenido, re.DOTALL)
        if bib:
            obj["bibtex_entry"] = bib.group(1).strip()

        match = re.findall(r"\$\$(.*?)\$\$", contenido, flags=re.DOTALL)
        if match:
            obj["contenido_latex"] = match[0].strip()

        demo = re.search(r"\*\*Demostración\*\*:(.*?)(\n\n|$)", contenido, flags=re.DOTALL)
        if demo:
            #pasos = re.findall(r"[-*]\\s+(.*)", demo.group(1))
            pasos = re.findall(r"^[*-]\s+(.*)", demo.group(1), flags=re.MULTILINE)
            obj["demostracion"]["pasos"] = [{"descripcion": p.strip()} for p in pasos]

            #obj["demostracion"]["pasos"] = [{"descripcion": p.strip()} for p in pasos]

        comentario_personal = re.search(r"\*\*Comentario personal\*\*:\s*(.*)", contenido, re.IGNORECASE)
        if comentario_personal:
            obj["comentario_personal"] = comentario_personal.group(1).strip()

        creado = re.search(r"\*\*Creado a partir de\*\*:\s*(.*)", contenido, re.IGNORECASE)
        if creado:
            obj["creado_a_partir_de"] = creado.group(1).strip()

        if guardar:
            os.makedirs(self.carpeta_salida, exist_ok=True)
            nombre_archivo = os.path.join(self.carpeta_salida, f"{obj['id']}.json")
            nombre_archivo = nombre_archivo.replace(":", "_")
            with open(nombre_archivo, "w", encoding="utf-8") as f:
                json.dump(obj, f, indent=2, ensure_ascii=False)
            print(f"✅ Guardado como: {nombre_archivo}")

        return obj

