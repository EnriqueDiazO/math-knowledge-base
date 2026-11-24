# Revisión individual de python:S5443 en el compilador

Incidencia `eb39a1a3-a6d9-4764-ae25-8f2387dd7917`, análisis
`c8ab7883-c880-4666-b3de-f64db3da9798`, revisión `18d2f49f`.
El aviso apunta a la línea 71 de `exporters_latex/sandbox.py`: el literal `/tmp`.

Ese argumento es el **destino dentro del namespace nuevo de bubblewrap**:

```text
--ro-bind <directorio-del-job>/outputs/empty /tmp
```

No se abre el `/tmp` del anfitrión para guardar datos. El origen es un directorio
vacío del job privado, montado de sólo lectura en `/tmp` del proceso aislado.
Además, la raíz se remonta como sólo lectura. Los únicos montajes de escritura
son seis archivos de salida concretos, con límite por archivo. No se habilita
una carpeta temporal pública para instrucciones del documento.

Evidencia ejecutada: `test_sandbox_clears_credentials_has_no_host_network_and_no_writable_directory`
lanza un proceso real con el comando de producción. Los intentos de crear
`/tmp/unexpected`, `/inputs/unexpected` y `/work/unexpected` deben devolver
exactamente `errno.EROFS`; no basta con cualquier error. La misma prueba verifica
que el proceso no recibe la variable de credenciales de prueba, no ve el archivo
privado del host y no alcanza un servidor loopback del host perteneciente al test.
La cohorte de aislamiento vuelve a pasar: 4 casos, JUnit y log en
`evidence/sonar/recovery-2026-11-24/sandbox-readonly.*`.

Se clasifica **sólo esta incidencia** como falso positivo por interpretar una
ruta destino del namespace como directorio temporal público del anfitrión.
No hay NOSONAR, supresión, cambio de perfil, desactivación de regla, exclusión
ni cambio del periodo o umbral. No se cambia una implementación que ya monta
esa ruta de forma segura para ocultar el literal al analizador.
