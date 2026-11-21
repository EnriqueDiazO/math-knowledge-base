# Dependencias del editor visual

No había editor documental visual ni motor matemático web reutilizable en la
esfera: ACE edita fuente, y las herramientas Cornell/Diario producen LaTeX/PDF.
Se reutiliza ese formato y su contrato de entornos, sin migrar las notas a HTML.

- MathLive **0.111.4**: exclusivamente edición/presentación de expresiones. Se
  desactiva Compute Engine, audio y carga automática de fuentes/CDN; no se usa
  simplificación algebraica. Macros no comprendidas conservan su fuente.
- Tiptap core + starter-kit **3.35.0**: documento ProseMirror, párrafos, títulos,
  listas, énfasis, selección e historial deshacer/rehacer. Sin servicios cloud,
  colaboración, IA ni conversión de base de datos a HTML.
- DOMPurify **3.4.18**: sanitiza la salida HTML interna de MathLive, además de la
  construcción de prosa mediante el esquema/DOM seguro del documento.

Son cuatro dependencias directas nuevas y 45 entradas nuevas en el lock de npm.
Ninguna dependencia existente cambió de versión. Se publican fuentes de letra y
licencias con los recursos locales del componente; las pruebas bloquearán las
solicitudes remotas. No se sustituye Canvas ni se incorpora un motor de física.

Fuentes primarias: [MathLive](https://mathlive.io/mathfield/),
[API y serialización](https://mathlive.io/mathfield/guides/interacting/),
[seguridad](https://mathlive.io/mathfield/guides/security/),
[macros](https://mathlive.io/mathfield/guides/macros/),
[Tiptap](https://tiptap.dev/docs/editor/getting-started/overview),
[NodeViews](https://tiptap.dev/docs/editor/extensions/custom-extensions/node-views/javascript),
[historial](https://tiptap.dev/docs/editor/extensions/functionality/undo-redo),
[DOMPurify](https://github.com/cure53/DOMPurify).
Las versiones se contrastaron con el registro npm y los paquetes instalados; no
se infiere de la documentación web que MathLive admita todo TeX.
