# Runtime local seguro

MathMongo administra Streamlit y Advanced Reader como un único runtime local.
Nunca ejecuta esos procesos con privilegios ni usa `pkill` o `killall`. La única
operación que puede elevarse es `systemctl start mongod` cuando el servicio está
realmente detenido.

## Estado e identidad

El supervisor crea `local-runtime-v1.json` bajo `$XDG_RUNTIME_DIR/mathmongo/`
(o el fallback XDG de MathMongo), con permisos `0600`. El registro contiene la
ruta canónica del repositorio, el identificador aleatorio de ejecución, la
versión de formato, base, puertos, timestamp y la identidad de cada proceso.

Cada identidad incluye PID, tick de inicio del kernel, comando y CWD. Antes de
confiar en el registro, MathMongo vuelve a comprobar esos valores en `/proc`,
los listeners de ambos puertos y los health checks locales. Así un PID reciclado
o un proceso de otro proyecto no puede convertirse en propiedad del runtime.

`mathmongo runtime status` clasifica el resultado como `stopped`, `owned`,
`stale`, `foreign`, `orphan` o `ambiguous` y muestra sólo diagnóstico saneado.
No imprime variables de entorno ni credenciales.

## Comandos

```bash
make status
make start
make run
make stop
make restart

mathmongo runtime status
mathmongo runtime doctor
mathmongo runtime mongo-ensure
mathmongo runtime start
mathmongo runtime run
mathmongo runtime stop
mathmongo runtime restart
mathmongo desktop-launch
```

`make status` es de sólo lectura: muestra por separado el estado de
`mongod`, el ping a la URI saneada, la base seleccionada y la identidad del
runtime. Nunca solicita autorización. Devuelve error si MongoDB no responde,
incluido el caso en el que systemd dice `active` pero el ping falla.

`make start` asegura MongoDB y deja el runtime verificado en segundo plano.
`make run` aplica el mismo preflight y conserva la ejecución en primer plano;
`Ctrl+C` detiene sólo sus servicios propios. Si MongoDB ya responde, ambos
continúan sin ejecutar `sudo` ni `pkexec`. Si `mongod` está `inactive` y hay una
terminal interactiva, el modo `auto` informa la acción y ejecuta únicamente:

```bash
sudo systemctl start mongod
```

En una sesión no interactiva el modo `auto` falla con una instrucción y no
invoca `sudo`. Se puede deshabilitar todo intento de elevación con
`MONGO_AUTO_START=0` o `MONGO_AUTH_MODE=none`. Los otros modos aceptados son
`sudo` y `pkexec`.

`make stop` sólo opera sobre estado `owned` confirmado y nunca detiene MongoDB.
`make restart` asegura MongoDB, detiene únicamente el runtime propio si existe y
lo vuelve a iniciar; si ya estaba detenido, simplemente lo inicia. Un proceso
extranjero en 8501/8766 se informa con su identidad disponible y jamás se mata.

Un `orphan` coincide con las firmas canónicas del repositorio, pero no cuenta
con supervisor ni metadata válida. Nunca se termina automáticamente. Tras
revisar `mathmongo runtime status`, se puede reemplazar de forma explícita con:

```bash
mathmongo runtime restart --recover-orphan
```

La parada normal envía `SIGTERM` al supervisor verificado y espera el cierre de
sus hijos. `--force` habilita `SIGKILL` únicamente para los PIDs que siguen
coincidiendo con la identidad original; no se obtienen PIDs desde un escaneo de
puertos al forzar el cierre.

## Acceso directo

El generador canónico instala un `.desktop` que ejecuta
`mathmongo desktop-launch`, sin shell y con `Terminal=false`:

```bash
./scripts/make_desktop_shortcut.sh --install --desktop
```

El launcher reutiliza el mismo ensure y el mismo controlador de runtime. Si
MongoDB responde, abre MathMongo sin diálogo; si `mongod` está detenido, usa
`pkexec systemctl start mongod` para solicitar autorización gráfica. Cancelar
detiene el flujo antes de crear metadata o iniciar la aplicación. Si `pkexec`
no está disponible, muestra una instrucción para iniciar MongoDB desde una
terminal.

Los fallos se notifican con `notify-send` cuando está disponible y quedan
saneados en `$XDG_STATE_HOME/mathmongo/logs/desktop-launch.log` (fallback
`~/.local/state/mathmongo/logs/`). La contraseña nunca se recibe ni se guarda
en MathMongo. El launcher aborta si se intenta ejecutar toda la aplicación como
root.

## Puertos y diagnóstico

Los defaults pueden cambiarse por invocación:

```bash
make start STREAMLIT_PORT=8502 ADVANCED_READER_PORT=8767
make run STREAMLIT_PORT=8502 ADVANCED_READER_PORT=8767
```

Si `make status` muestra `Servicio mongod: active` y `Ping MongoDB: sin
respuesta`, MathMongo no vuelve a iniciar el servicio: revisa la URI, el puerto,
la configuración de MongoDB y sus logs. No modifiques `/etc/mongod.conf` como
parte del launcher.
