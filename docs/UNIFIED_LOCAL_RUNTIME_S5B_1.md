# Runtime local unificado S5B.1

## Problema resuelto

Hasta S5B, `make run` iniciaba únicamente Streamlit. El Advanced Reader debía
arrancarse en otra terminal y, si se omitía `--database MathV0`, podía quedar
escuchando en `8766` sobre otra base. En ese caso su health era válido, pero el
Document seleccionado por Streamlit respondía `document_not_found`.

S5B.1 incorpora un supervisor Python en foreground. Un solo comando inicia y
vigila los dos servicios con la misma base inicial:

```bash
make run
```

Los defaults son `MathV0`, Streamlit en `http://127.0.0.1:8501` y Advanced
Reader en `http://127.0.0.1:8766`. El Makefile sólo entrega argumentos al
supervisor; no crea procesos background, PID files ni daemons.

## Comandos

El flujo normal es:

```bash
make run
```

Los servicios siguen disponibles por separado para diagnóstico:

```bash
make run-streamlit
make advanced-reader DATABASE=MathV0
```

Todos los parámetros son overrides de una sola ejecución; no escriben el
archivo de configuración del usuario:

```bash
make run \
  DATABASE=otra_base \
  STREAMLIT_PORT=8502 \
  ADVANCED_READER_PORT=8767 \
  LOG_LEVEL=warning
```

Las variables soportadas son `DATABASE`, `STREAMLIT_HOST`, `STREAMLIT_PORT`,
`ADVANCED_READER_HOST`, `ADVANCED_READER_PORT` y `LOG_LEVEL`. Ambos hosts deben
ser loopback (`127.0.0.1`, `localhost` o `::1`); no se admite exposición LAN ni
`0.0.0.0`.

Streamlit recibe la base mediante el contrato existente `MONGODB_DB` y la URL
del lector mediante `MATHMONGO_ADVANCED_READER_URL`. Así, su conexión inicial y
el Advanced Reader usan `DATABASE`. El selector de base de Streamlit permanece
disponible.

## Orden de inicio y health

El supervisor valida argumentos y puertos, inicia primero Advanced Reader y no
continúa hasta recibir exactamente:

```json
{
  "status": "ok",
  "service": "mathmongo-advanced-reader",
  "database": "MathV0",
  "frontend_ready": true
}
```

Después inicia Streamlit y espera `GET /_stcore/health`. Cuando ambos están
listos muestra URLs y si el lector fue `started` o `reused`. Los logs de hijos
propios permanecen visibles con prefijos `[advanced-reader]` y `[streamlit]`.
La salida del launcher no expone URI MongoDB, credenciales, HOME, rutas XDG ni
rutas de blobs.

Reading Space aplica una comprobación adicional al PDF activo: exige health en
la base activa y consulta `GET /api/advanced-reader/documents/{document_id}`.
El enlace sólo se habilita si el Document existe, es PDF y su integridad es
`ok`. Los estados de servicio no iniciado, timeout, base distinta, Document
ausente, tipo no PDF e integridad inválida se muestran por separado. `Open PDF`
y el visor `st.pdf` continúan siendo el fallback independiente.

## Puertos ocupados y reutilización

Un listener desconocido nunca se termina automáticamente.

Si el puerto del Advanced Reader está ocupado, el supervisor consulta su health.
Sólo reutiliza el servicio cuando identidad, base y frontend coinciden
exactamente. El proceso reutilizado no pertenece al supervisor y nunca se
detiene al salir. Si la base difiere, el arranque se bloquea con las bases
observada/esperada y propone esta inspección segura:

```bash
ss -ltnp | grep ':8766'
```

Si el puerto de Streamlit está ocupado, el supervisor adopta la política
conservadora: aunque `/_stcore/health` responda, no puede probar de forma segura
que sea esta instalación, así que no lo reutiliza ni lo detiene. Libera el
puerto manualmente o elige otro:

```bash
make run STREAMLIT_PORT=8502
```

## Ctrl+C y fallos

El supervisor permanece en foreground. Con `Ctrl+C` o `SIGTERM`:

1. marca el cierre;
2. envía `SIGTERM` sólo a los grupos de procesos que creó;
3. espera un plazo acotado;
4. usa `SIGKILL` únicamente si uno de esos hijos no terminó;
5. recoge procesos y lectores de logs.

`Ctrl+C` devuelve 130 y `SIGTERM` devuelve 143. Si un hijo termina inesperadamente, se identifica el
servicio, se cierra el otro hijo propio y el supervisor devuelve un código no
cero. Un Advanced Reader reutilizado se conserva en todos los casos.

## Limitación de base en S5B.1

La base del Advanced Reader queda fijada al iniciar el proceso. Si una sesión
cambia de base con el selector de Streamlit, el lector no cambia de base ni se
reinicia: Reading Space detecta el mismatch y deshabilita el enlace avanzado.
Para alinear ambos servicios, detén el runtime y vuelve a iniciarlo con
`DATABASE=<base>`. El routing multibase no forma parte de S5B.1.

## Solución de problemas

- **Puerto 8766 ocupado por otro proceso:** inspecciona con
  `ss -ltnp | grep ':8766'`; detén manualmente el proceso correcto o usa
  `ADVANCED_READER_PORT=8767`.
- **Reader en otra base:** detén ese lector manualmente o reinicia ambos con el
  mismo `DATABASE`. El supervisor nunca ejecuta `pkill`, `killall` ni `kill`
  sobre procesos ajenos.
- **Puerto 8501 ocupado:** usa `ss -ltnp | grep ':8501'` y libera el proceso que
  reconoces, o ejecuta `make run STREAMLIT_PORT=8502`.
- **Document no encontrado:** confirma la base activa en Streamlit y reinicia el
  runtime con esa misma base.
- **Timeout o integridad:** `Open PDF`/`st.pdf` sigue operativo; revisa el estado
  local del lector y del PDF antes de reintentar.

S5B.1 no cambia modelos, colecciones, PDFs, blobs, anotaciones ni el frontend
PDF.js, y no inicia S5C.
