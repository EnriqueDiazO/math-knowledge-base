# Instalación docente reproducible

## Requisitos del sistema

Usa Ubuntu 22.04.5 LTS, Python 3.10.12, MongoDB 7.0.35/FCV 7.0 y TeX Live
2022 para la línea verificada. MongoDB y TeX Live son dependencias de sistema;
instálalas y pruébalas antes de una clase, no durante ella.

## Entorno Python

No reutilices un entorno de investigación sin verificarlo. Desde un checkout
limpio:

```bash
python3 -m venv mathdbmongo
. mathdbmongo/bin/activate
python -m pip install --upgrade pip
python -m pip install -c constraints/teaching-2026.txt -e .
python -m pip install -r requirements-dev.txt
python -m pip check
```

Comprueba la versión crítica:

```bash
python -c "import streamlit; print(streamlit.__version__)"
# 1.59.2
```

## Configuración de la base

El producto es MathMongo. La base se elige sin renombrarla mediante variables
de entorno o `~/.config/mathmongo/config.json`; la precedencia es argumento
explícito, entorno, archivo y default. Copia el ejemplo sin secretos y ajusta
solamente el nombre de base que corresponda:

```bash
cp .env.example .env
# MONGODB_DB=MathV0
mathmongo config
```

Antes de una actualización, consulta
[backup y recuperación](BACKUP_AND_RECOVERY.md): primero backup, restauración
temporal, verificación y smoke test; después cambia `MONGODB_DB` si procede.

## Smoke test local

Usa XDG temporal y una base inaccesible para comprobar que el arranque comunica
el error sin filtrar secretos. Para una sesión real, usa una base ya aprobada y
arranca `make run-streamlit DATABASE=MathV0`.
