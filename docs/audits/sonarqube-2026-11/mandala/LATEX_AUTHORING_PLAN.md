# Paridad de autoría LaTeX: lote del 24 de noviembre de 2026

Checkpoint recuperado: `0bae86e1`, rama `feature/knowledge-sphere-2026-11`,
árbol limpio. Análisis vigente `68db7833-292e-46f7-8b7b-93e7998ded5e`,
fuente `0e08a639`, 76,4 % general / 81,7 % nueva, Gate OK. Se conservan
referencia, perfiles, reglas, umbrales, exclusiones y evidencias anteriores.

## Carencia demostrada y decisión

`DocumentEditor` expone una textarea como fuente completa. Conserva LaTeX y
permite compilar preámbulos mediante `compose_project`, pero carece de
resaltado, líneas, búsqueda/reemplazo y completado especializado. Insertar un
bloque protegido no cubre esta carencia. El frontend no tiene ACE/CodeMirror.

Se integra CodeMirror 6 exclusivamente como superficie de código, manteniendo
Tiptap/MathLive para lo visual. Reimplementar selección, historial, búsqueda,
reemplazo y pintado de cientos de líneas mediante overlays propios añadiría
riesgos de sincronización sin ventaja. Se declaran sólo los módulos usados,
versiones exactas, licencias instaladas verificadas y avisos redistribuidos por
el generador existente. Instalación local con `--ignore-scripts`, sin globales.
No se añade otro formato documental ni otro backend. Referencias primarias:
[proyecto oficial](https://github.com/codemirror/dev), documentación y tipos
de los paquetes fijados. La documentación web directa respondió 403; se
contrastarán los contratos en los tipos y fuentes instalados.

## Aceptación y orden

1. Corpus inmutable: cinco copias históricas válidas, concepto helicoidal real
   de 107 líneas y documentos reales de más de 200 líneas del respaldo privado;
   ejemplos adicionales derivados de plantillas reales para cubrir diez casos.
   Registrar hashes, procedencia y dependencias sin versionar datos privados.
2. Fuente completa: código libre, líneas, resaltado, búsqueda/reemplazo, historial,
   snippets/completado de comandos y begin/end, teclado, altura y selección.
   Preservar CRLF/mixed, Unicode y macros; snapshot y borrador aislados.
3. Navegadores: recorridos A–H con guardado/relectura Mongo real, edición
   localizada, alternancia y compilación; error corregible y conflicto explícito.
   Los paquetes ausentes no invalidan almacenamiento ni autorizan convertir código.
4. Cerrar ese checkpoint antes de ampliar operaciones Cornell/CPI. Reutilizar
   servicios canónicos para el siguiente corte de asociaciones/medios/notas;
   no declarar paridad de las familias ni retirar compatibilidad por adelantado.
5. Pruebas focalizadas por cambio, baterías integrales en checkpoint, Sonar
   procesado comparable y AppImage actualizada con prueba de reinicio propia.

Todas las escrituras pertenecen a mongod/PID/dbpath, base UUID, XDG y recursos
temporales. MathV0 no recibe escrituras; las entradas privadas se extraen sólo
del ZIP en modo lectura. No push, merge, reset ni reinstalación de Sonar.
El 95 % sigue siendo objetivo abierto, con déficit por archivo registrado.
