# Ruff: inventario por regla y consecuencia

Baseline: **2165** avisos; final: **2156**. Misma versión 0.4.10 y ruff.toml, sin autofix global.

Los avisos indican ubicaciones; no equivalen a defectos funcionales confirmados. El análisis completo incluye módulos propios y pruebas.

| Regla | Inicial | Final | Consecuencia y decisión |
|---|---:|---:|---|
| B904 | 1 | 1 | Encadenamiento de excepción del fallback; deuda diagnóstica, no causa confirmada del fallo. No se ocultó. |
| D100 | 25 | 25 | Documentación/docstrings (incluidos adaptadores legados); mantenimiento, no ejecución. |
| D101 | 28 | 28 | Documentación/docstrings (incluidos adaptadores legados); mantenimiento, no ejecución. |
| D102 | 23 | 23 | Documentación/docstrings (incluidos adaptadores legados); mantenimiento, no ejecución. |
| D103 | 106 | 106 | Documentación/docstrings (incluidos adaptadores legados); mantenimiento, no ejecución. |
| D104 | 6 | 6 | Documentación/docstrings (incluidos adaptadores legados); mantenimiento, no ejecución. |
| D107 | 9 | 9 | Documentación/docstrings (incluidos adaptadores legados); mantenimiento, no ejecución. |
| D200 | 8 | 8 | Documentación/docstrings (incluidos adaptadores legados); mantenimiento, no ejecución. |
| D202 | 3 | 3 | Documentación/docstrings (incluidos adaptadores legados); mantenimiento, no ejecución. |
| D205 | 14 | 14 | Documentación/docstrings (incluidos adaptadores legados); mantenimiento, no ejecución. |
| D212 | 33 | 33 | Documentación/docstrings (incluidos adaptadores legados); mantenimiento, no ejecución. |
| D301 | 1 | 1 | Documentación/docstrings (incluidos adaptadores legados); mantenimiento, no ejecución. |
| D415 | 12 | 12 | Documentación/docstrings (incluidos adaptadores legados); mantenimiento, no ejecución. |
| E101 | 1437 | 1437 | 1437 en el JavaScript embebido de grafoconocimiento.py; mezcla de tabs/espacios en el literal. Compila y se probó el HTML; evitar reformateo masivo ajeno al defecto. |
| E402 | 1 | 1 | Espacios/saltos/formato. Se corrigieron sólo líneas tocadas por el lote, sin reformatear el proyecto. |
| E712 | 4 | 4 | Espacios/saltos/formato. Se corrigieron sólo líneas tocadas por el lote, sin reformatear el proyecto. |
| E721 | 6 | 6 | Comparación estricta de tipos en validadores que rechazan bool/subclases. No sustituir automáticamente por isinstance: cambia validación. |
| F401 | 2 | 1 | Import no usado: retirado os redundante del wrapper; se conserva output_tail en unified_document por posible reexport público. |
| F403 | 1 | 1 | Wildcard del wrapper Streamlit legado; preservado por su contrato de entrada. |
| F541 | 1 | 1 | f-string sin interpolación, cosmético; conservado. |
| F811 | 1 | 0 | Segundo import idéntico de List retirado; símbolo y anotaciones conservados. |
| F841 | 2 | 0 | Asignaciones puras no usadas retiradas; tests de grafo/Quarto y lectura de llamadas descartan efectos necesarios. |
| I001 | 13 | 12 | Orden de imports; no se reorganizan módulos completos sin necesidad. |
| UP006 | 119 | 119 | Modernización sintáctica; mantener Python 3.10 y contratos existentes. No es fallo funcional por sí solo. |
| UP007 | 74 | 74 | Modernización sintáctica; mantener Python 3.10 y contratos existentes. No es fallo funcional por sí solo. |
| UP009 | 2 | 2 | Modernización sintáctica; mantener Python 3.10 y contratos existentes. No es fallo funcional por sí solo. |
| UP015 | 3 | 3 | Modernización sintáctica; mantener Python 3.10 y contratos existentes. No es fallo funcional por sí solo. |
| UP035 | 16 | 15 | Modernización sintáctica; mantener Python 3.10 y contratos existentes. No es fallo funcional por sí solo. |
| UP038 | 45 | 45 | Modernización sintáctica; mantener Python 3.10 y contratos existentes. No es fallo funcional por sí solo. |
| W291 | 50 | 48 | Espacios/saltos/formato. Se corrigieron sólo líneas tocadas por el lote, sin reformatear el proyecto. |
| W292 | 4 | 3 | Espacios/saltos/formato. Se corrigieron sólo líneas tocadas por el lote, sin reformatear el proyecto. |
| W293 | 115 | 115 | Espacios/saltos/formato. Se corrigieron sólo líneas tocadas por el lote, sin reformatear el proyecto. |

Las supresiones y exclusiones de ruff.toml ya existían (E501/C901/E722). No se ampliaron.
Los fallos de rollback, compartición de medios, Markdown, rutas y HTML se confirman mediante pruebas de comportamiento aunque Ruff no los señalaba.

## Fase de pendientes

El recuento con Ruff 0.4.10 y los mismos ruff.toml/alcance es **2157**.
Respecto a 2156, únicamente I001 pasa de 12 a 13 por el orden de imports de
un test nuevo (test_sonar_http_contracts.py:3). Es deuda cosmética P3 y no altera
comportamiento. Las demás reglas mantienen exactamente el recuento de la tabla;
no se amplían ignores/exclusiones ni se ejecuta make lint (que hace --fix).
Resultado bruto local: evidence/sonar/followup-2026-11/ruff.json.
