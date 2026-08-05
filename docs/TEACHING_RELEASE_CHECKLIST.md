# Checklist de release docente

- [ ] Confirmar `mathmongo config`: producto MathMongo y base activa esperada.
- [ ] Crear y verificar backup MongoDB + XDG; restaurar primero en una base nueva.
- [ ] Ejecutar `pip check`, suite dirigida, suite completa y smoke Streamlit.
- [ ] Confirmar Streamlit 1.59.2 y las versiones de la matriz de compatibilidad.
- [ ] Ejecutar `make status` y confirmar que no solicita contraseña.
- [ ] Con MongoDB ya activo, confirmar que `make start` no invoca `sudo`/`pkexec` y reporta ambas URL.
- [ ] Confirmar que `make stop` detiene sólo el runtime identificado y deja MongoDB activo.
- [ ] Regenerar el acceso directo con `./scripts/make_desktop_shortcut.sh --install --desktop` y probar MongoDB activo/runtime ya activo.
- [ ] Probar MongoDB detenido sólo con autorización explícita; cancelar el diálogo debe impedir el arranque de MathMongo.
- [ ] Revisar Source Catalog, PDF y Reading Space mediante doctor sin escritura.
- [ ] Confirmar que no se ha renombrado, migrado ni fusionado MathV0.
- [ ] Conservar backup, manifiesto, HEAD y tag de rollback propuesto.
- [ ] No actualizar MongoDB, PyMongo ni Streamlit durante el curso sin repetir esta lista.
