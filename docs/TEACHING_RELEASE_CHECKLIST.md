# Checklist de release docente

- [ ] Confirmar `mathmongo config`: producto MathMongo y base activa esperada.
- [ ] Crear y verificar backup MongoDB + XDG; restaurar primero en una base nueva.
- [ ] Ejecutar `pip check`, suite dirigida, suite completa y smoke Streamlit.
- [ ] Confirmar Streamlit 1.59.2 y las versiones de la matriz de compatibilidad.
- [ ] Revisar Source Catalog, PDF y Reading Space mediante doctor sin escritura.
- [ ] Confirmar que no se ha renombrado, migrado ni fusionado MathV0.
- [ ] Conservar backup, manifiesto, HEAD y tag de rollback propuesto.
- [ ] No actualizar MongoDB, PyMongo ni Streamlit durante el curso sin repetir esta lista.
