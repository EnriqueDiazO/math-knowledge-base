# Matriz de compatibilidad docente

La línea `teaching-2026` es una configuración **verificada**, no una
autorización para actualizar durante el curso. MathMongo sigue siendo el
producto y `MathV0` puede seguir siendo el nombre físico de la base activa.

| Componente | Estado | Versión / rango |
|---|---|---|
| Ubuntu | verified | 22.04.5 LTS |
| Python | verified | 3.10.12; declarado `>=3.10,<3.14` |
| Streamlit | verified / recommended | 1.59.2; declarado `>=1.59,<1.60` |
| PyMongo | verified | 4.17.0; declarado `>=4.17,<4.18` |
| MongoDB Server | verified | 7.0.35 |
| MongoDB FCV | verified | 7.0 |
| Pydantic | verified | 2.13.4; declarado `>=2.13,<3` |
| Pillow | verified | 12.3.0; declarado `>=12.3,<13` |
| pandas | verified | 2.3.3; declarado `>=2.3,<2.4` |
| mongosh | verified | 2.8.3 |
| MongoDB Database Tools | verified | 100.17.0 |
| TeX Live | verified | 2022 |
| Otras versiones dentro de los rangos | unverified | requieren ensayo completo antes de clase |
| Streamlit fuera de 1.59.x | known incompatible for teaching | no actualizar sin nuevo gate |

`pyproject.toml` es la fuente de verdad de dependencias directas de runtime;
`constraints/teaching-2026.txt` fija las versiones verificadas; y
`requirements-dev.txt` separa pytest/Ruff de runtime. `poetry.lock` no es la
fuente de instalación docente hasta que se regenere y valide explícitamente.

Antes de actualizar MongoDB, PyMongo o Streamlit: crea un backup verificado,
restáuralo en una base temporal, ejecuta la suite y un smoke test, prueba una
instalación limpia y conserva un rollback mediante tag más backup.
