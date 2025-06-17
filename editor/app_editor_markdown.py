class EditorConcepto:
    def __init__(self, base_path: str):
        pass

    def cargar_formato(self, tipo: str) -> str:
        pass

    def guardar_concepto(self, concepto_latex: str, metadata: dict) -> None:
        pass

    def previsualizar_concepto(self, concepto_latex: str) -> str:
        pass

    def convertir_a_json(self, concepto_latex: str, metadata: dict) -> dict:
        pass
