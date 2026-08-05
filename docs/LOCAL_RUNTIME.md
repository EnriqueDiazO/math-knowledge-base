# Runtime local seguro

MathMongo administra Streamlit y Advanced Reader como un único runtime local.
No usa `sudo`, `pkill` ni `killall`.

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
mathmongo runtime start
mathmongo runtime stop
mathmongo runtime restart
```

`make start` y `make status` sólo realizan diagnósticos. Si MongoDB ya está
activo no piden contraseña ni ejecutan `sudo`; si está inactivo indican que debe
iniciarse por el mecanismo del sistema antes de volver a intentar.

`make run` reutiliza `mathmongo runtime start`: si el runtime propio ya está
activo lo informa y no crea otro. `make stop` y `make restart` sólo operan con
estado `owned` confirmado.

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
