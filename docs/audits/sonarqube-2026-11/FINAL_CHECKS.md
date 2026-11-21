# Verificación final

Fecha de trabajo: 2026-11-21 (America/Mexico_City). Rama
`audit/sonarqube-2026-11`; origen limpio `main@1bc8026f`.

| Verificación ejecutada | Resultado / evidencia local |
|---|---|
| Suite Python completa con coverage/JUnit | 1783 passed, 59 skipped, 0 failures/errors, 132.81 s; pytest.xml y final-suite-and-prior-scan.log |
| Regresiones de parser tras strict=False explícito | 15 passed; parser-explicit-zip-check.log |
| E2E Mongo standalone final | 9 passed, 7.57 s; final-mongo-e2e.log; datos/bases/dbpath temporales retirados |
| Reproducción rollback antes/después | 4 fallos / 1 control antes; 5 aprobados después; luego 6 al añadir comandos; logs mongo-regressions-* y commands-and-data-e2e.log |
| Pruebas de grafos y seguridad HTML | 12 passed; graph-security-after.log; fallos anteriores guardados |
| Grafo HTML en Chrome | 2 nodos, canvas 1264 px, sin page errors; 6 scripts inline pasan node --check; graph-browser-smoke.log |
| Frontend | tsc, ESLint, 107 tests Vitest, build/publish y npm ci aprobados; frontend-security-*.log / npm-ci.log |
| Paquete/constraints | 12 tests aprobados; dependency-packaging-tests.log |
| Runtime integrado + Streamlit/lector en Chrome | OK, PDFs pintados/text layer/worker/range, apertura desde Biblioteca/Leer; final-runtime-e2e.log |
| Reutilización y base incompatible | Lector reutilizado sobrevivió al supervisor; base incorrecta bloquea arranque de Streamlit; limpieza de puertos comprobada |
| Lector ampliado y round-trip | OK, anotaciones/vínculos/rehidratación y geometría importada; final-reader-browser-e2e.log |
| pip / Poetry | pip check pasa; poetry check --lock pasa con avisos de deprecación previos; instalación editable actualizada |
| Auditoría dependencias | npm 0; Python 76 entradas de avisos en 7 paquetes, documentadas sin filtros |
| Ruff | 2156 avisos frente a 2165; mismas reglas y exclusiones; RUFF.md agrupa los 32 tipos |
| Shell / harness JS | bash -n sobre todos los .sh y node --check del probe aprobados |
| Scanner nativo limpio | SHA256 fijado, extracción nueva, --version y helper JRE ejecutable verificados |
| XML Python | Todos los módulos propios presentes, rutas relativas inequívocas y sensor de Sonar sin errores de resolución |
| Sonar final | CE SUCCESS y revisión 4b8cb48c confirmada por API; Gate ERROR sólo por cobertura nueva 31.2% < 80% |
| Persistencia Sonar | down/up conservó proyecto, último análisis y credenciales; persistence-restart.log |
| Secretos | .env y access.local.json con 0600 e ignorados por Git; ningún valor privado en informes/commits |
| Host | vm.max_map_count=524288 vivo y persistente; archivo específico creado por el usuario tras revisar configuración existente |

Sonar permanece en <http://127.0.0.1:19000>. El servicio PostgreSQL sólo es accesible
por la red privada de Compose. MongoDB habitual no se arrancó ni se usó para escribir.
Los procesos de las pruebas son propios y se detuvieron; los puertos habituales no
se ocuparon. Los servicios Docker ajenos no fueron detenidos ni reconfigurados.

Las 59 omisiones de la suite general son 50 tests que requieren el ZIP autoritativo
privado ausente y 9 E2E opt-in. Estos nueve se ejecutaron aparte y pasan. No se presenta
el ZIP ausente como validado ni el Gate fallido como aprobado.

La cobertura de nuevas líneas del tooling requiere trabajo adicional (P10). Los
advisories Python pendientes requieren cualificación de versiones/Python mayores;
la propuesta está en DEPENDENCIES.md. Las demás interpretaciones y límites están en
FINDINGS.md. El alcance/perfiles/umbrales del scanner se conservaron comparables.
