# Instalación docente reproducible

## Requisitos del sistema

Usa Ubuntu 22.04.5 LTS, Python 3.10.12, MongoDB 7.0.35/FCV 7.0 y TeX Live
2022 para la línea verificada. MongoDB y TeX Live son dependencias de sistema;
instálalas antes de una clase. MathMongo puede iniciar un servicio `mongod` ya
instalado, pero no instala ni actualiza MongoDB.

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

Comprueba primero sin efectos laterales:

```bash
make status
```

Después elige ejecución detached o foreground:

```bash
make start DATABASE=MathV0
make run DATABASE=MathV0
```

Si MongoDB ya responde, no se pide contraseña. Si el servicio está detenido,
una terminal interactiva informa la acción y solicita autorización sólo para
`sudo systemctl start mongod`; la contraseña no se guarda. MathMongo,
Streamlit y Advanced Reader siguen ejecutándose como el usuario normal. En CI o
sin TTY no se intenta `sudo`; usa `MONGO_AUTO_START=0` para hacer explícita esa
política.

`make stop` detiene únicamente un runtime MathMongo con identidad confirmada y
no detiene MongoDB. `make restart` asegura MongoDB y reemplaza sólo el runtime
propio. Para probar con puertos alternos:

```bash
make run DATABASE=MathV0 STREAMLIT_PORT=18501 ADVANCED_READER_PORT=18766
```

Instala o regenera el acceso directo de usuario con:

```bash
./scripts/make_desktop_shortcut.sh --install --desktop
```

El acceso directo usa autorización gráfica `pkexec` sólo si `mongod` está
detenido, abre el runtime verificado y registra fallos saneados en
`$XDG_STATE_HOME/mathmongo/logs/desktop-launch.log`. Si el servicio figura
activo pero el ping falla, consulta `make status`; el launcher no intentará
reiniciarlo ni cambiará `/etc/mongod.conf`.

Para un smoke aislado, usa HOME/XDG temporales, mocks de `systemctl` y puertos
temporales. No detengas el MongoDB real ni ocupes 8501 durante una validación
automatizada.
