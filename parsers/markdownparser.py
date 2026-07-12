import hashlib
import json
import os
import re
from pathlib import Path

from mathmongo.paths import get_data_dir
from mathmongo.paths import resolve_home_path
from mathmongo.paths import validate_mutable_path


class MarkdownParser:
    """
    → Clase para convertir archivos Markdown estructurados en objetos JSON.
    Admite campos teóricos y de ejemplos con estilo Zettelkasten.
    """

    def __init__(self, carpeta_salida: str | Path | None = None) -> None:
        destination = (
            get_data_dir() / "user_templates" / "plantillas"
            if carpeta_salida is None
            else resolve_home_path(carpeta_salida)
        )
        self.carpeta_salida = str(validate_mutable_path(destination))

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

    def generar_ejemplo_md(
        self,
        nombre_archivo: str,
        carpeta_destino: str | Path | None = None,
    ) -> None:
        """
        Genera un archivo Markdown de ejemplo con formato predefinido.

        Parámetros:
        - nombre_archivo (str): Nombre del archivo Markdown a crear (ej. 'formato_proposicion.md')
        - carpeta_destino (str): Carpeta donde se guardará el archivo
        """
        destination = (
            get_data_dir() / "user_templates" / "md_files"
            if carpeta_destino is None
            else resolve_home_path(carpeta_destino)
        )
        destination = validate_mutable_path(destination)
        os.makedirs(destination, exist_ok=True)

        ejemplos = {
        "formato_proposicion.md":"""# Desigualdad del triángulo generalizado

**Tipo**: proposicion  
**Comentario**:   
**Comentario Previo**: 
**Categorías**: Topología, Espacios métricos  
**Tags**: desigualdad triangular, métrica, espacio métrico  
**Relacionado con**: proposicion::bf7c0b19  
**Referencia**: Wilkiewicz, 2019, Curso de análisis y 150 problemas resueltos,1,9,Wilkiewicz2019   

$$
\\textbf{Proposición 1.3.} \\text{ Para } x, y, u, v \\in X arbitrarios\\\\
|d(x, y) - d(u, v)| \\leq d(x, u) + d(y,v).
$$

**Demostración**:
- Dos veces aplicamos la desigualdad del triángulo para obtener  \\( d(x, y) \\leq d(x, u) + d(u, y) \\leq d(x,u) + d(u,v) + d(y,v) \\)
- Luego \\(d(x,u) - d(u,v) \\leq d(x,u) + d(y,v) \\)
- Intercambiando los papeles de las parejas \\( (x,y) \\) y \\( (u,v) \\) y gracias a la simetría de la distancia obtenemos que  
 implica 
\\( d(x, y) - d(x, u) \\leq d(u, y) \\)
- Por la misma desigualdad tenemos \\( d(x, u) \\leq d(x, y) + d(u, y) \\), de donde \\( d(x, u) - d(x, y) \\leq d(u, y) \\)
- Finalmente \\( | d(x,y) - d(u,v) | \\leq d(x,u) + d(y,v) \\)

```bibtex
@book{Wilkiewicz2019,
  author = {Wilkiewicz, Antoni Wawrzyñczyk},
  title = {Curso de análisis y 150 problemas resueltos},
  year = {2019},
  publisher = {McGraw-Hill}
}
```

**Enlaces de salida**:   
**Enlaces de entrada**: proposicion::bf7c0b19  
**Comentario personal**:  
**Inspirado en**:   
**Creado a partir de**: 
"""
        }

        safe_name = Path(nombre_archivo)
        if safe_name.name != nombre_archivo or safe_name.is_absolute():
            raise ValueError("nombre_archivo must be a plain filename")
        ruta_archivo = destination / safe_name
        if not os.path.exists(ruta_archivo):
            with open(ruta_archivo, "w", encoding="utf-8") as f:
                f.write(ejemplos[nombre_archivo].strip() + "\n")
            print(f"📄 Archivo generado: {ruta_archivo}")
        else:
            print(f"⚠️ Ya existe: {ruta_archivo}")
