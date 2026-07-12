# Fase S1C2P — bootstrap operativo del Source Catalog en MathV0

Fecha de operación: 2026-07-12 (UTC)

Resultado: satisfactorio

Base objetivo: `MathV0`

## Decisión y alcance

Por decisión humana explícita se omitió la aplicación previa sobre una copia
aislada. Se aceptó el riesgo de una aplicación directa en la base real únicamente
porque la operación era aditiva, existía una ventana de escritura congelada y se
cumplieron todas las puertas del checkpoint S1C2P.

La única frontera autorizada fue:

- crear `sources`, `references` y `source_catalog_migration_manifest`;
- crear los 15 índices aprobados de Sources/References;
- no modificar documentos ni índices de las diez colecciones legacy.

No se usaron bypasses, flags force/skip, rollback destructivo, renombre de base,
monkeypatch de la puerta ni conexión de escritura alternativa.

## Código y entradas inmutables

- Commit de código utilizado:
  `9f924fd4a391d879e030a874ea74ecb95e249e5b`
  (`feat: add guarded MathV0 catalog bootstrap and portability`).
- ZIP autoritativo del plan: `mathkb_export_20260712_073927.zip`.
- SHA-256 del ZIP autoritativo:
  `9b8660712171c7ab6db6fb3148deac23921330e1a640615ae6ae36c97e2165c8`.
- SHA-256 semántico del plan:
  `e91599d50c58bb88014911590d34c9f0fc46b1c989dec8f3f25fed007a33b44f`.
- Planner: `s1c1-v1`.

El ZIP autoritativo permaneció intacto, no rastreado y fuera de todos los commits.

## Ventana de escritura y backup pre-apply

No había un proceso Streamlit/MathMongo de usuario activo ni listeners en los
puertos 8501–8504; por tanto no fue necesario detener un proceso de usuario.
`mongod` permaneció activo. No se abrió otro escritor durante la ventana.

- Freeze UTC: `2026-07-12T20:39:08.652623Z`.
- Directorio privado: `$XDG_STATE_HOME/mathmongo/s1c2p-20260712-qakHK9/`
  (0700).
- Backup pre-apply: `mathkb_export_20260712_203908.zip` (0600).
- Tamaño: 7,202,492 bytes.
- SHA-256:
  `26b8a1a21a14551c371976ea2163e88aea995131ef97e5f6b29c83ff611c39ce`.
- Formato: `mathkb_legacy_export`, versión 1, `database_name=MathV0`.
- Snapshot: inicio `2026-07-12T20:39:08.879645Z`; final
  `2026-07-12T20:39:08.932351Z`.
- Media físicos: 15.
- SHA-256 agregado media:
  `dd4c7eda2d9b269aa84a77b29dfc0fe6cd51cc5751b9d781c49250d1123851b9`.
- Fingerprint portable legacy:
  `fcc4d833f6e35146d7a673cfc352f157f026e43373b0a46b1fe21fa9c6f34636`.

Conteos pre-apply:

| Colección | Conteo |
| --- | ---: |
| concepts | 186 |
| latex_documents | 187 |
| relations | 136 |
| knowledge_graph_maps | 2 |
| media_assets | 10 |
| latex_notes | 34 |
| backlog_items | 3 |
| deliverables | 2 |
| worklog_entries | 5 |
| weekly_reviews | 0 |

`sources`, `references` y el manifiesto estaban físicamente ausentes. El
validador confirmó archivo regular estable, propietario, modos, SHA, ZIP seguro,
metadata, conteos, fingerprints, inventario media, orden temporal y frescura.

## Decisiones humanas

El archivo privado `source_catalog_decisions.json` quedó fuera del repositorio y
con modo 0600.

- SHA-256 de sus bytes:
  `0c48afd132e150cef3295f3fe90f69d009d768db0ce6050501c4d6ccfbe1f2d4`.
- `decisions_sha256` canónico:
  `6071c9616a70b2796d9ddaf50149a12686c17cf4bf0b5be23303a3b21b340bfb`.
- `accept_all_safe_exact=true`.
- 2 sugerencias débiles: `keep_separate`.
- 5 revisiones de locator: `defer`.
- Sin claves desconocidas ni IDs finales aportados por el operador.

## Preflight final

Se repitieron `status`, `dry-run`, `compare-live` y `apply-status` inmediatamente
antes del apply. Los reportes privados se conservaron fuera del checkout.

- ZIP seguro y sin cambios: sí.
- ZIP SHA y plan SHA: exactos.
- Concepts: 186.
- Source candidates: 16.
- Reference candidates: 20.
- Bindings: 186.
- Conflictos: 0.
- Review items: 5; weak suggestions: 2.
- `snapshot_drift=false`.
- `live_database_drift=false`.
- `writes_attempted=0`.
- Conteos, partición de referencias, fuentes y fingerprints: coincidentes.
- `sources`, `references` y manifiesto: ausentes.
- Manifiestos observados por `apply-status`: 0.
- Backup fresco: validado.

## Apply real

El primer apply terminó con exit code 0 y stderr vacío.

- Outcome: `applied`.
- Estado durable: `applied`.
- Migration ID: `mig_d081709c-d5f3-4654-85ca-0e90398870da`.
- Manifest key:
  `source_catalog_manifest_4efe122cd120778dd5fae0fd9521e047d149f79ee196111fb0eabc42db54b184`.
- Inicio: `2026-07-12T20:43:40.807000Z`.
- Final: `2026-07-12T20:43:42.142000Z`.
- Sources creadas: 16; idénticas previas: 0.
- References creadas: 20; idénticas previas: 0.
- Manifiestos: 1.
- Índices aplicados: 15; faltantes: 0; conflictos: 0.
- SHA del plan de índices:
  `a7251e3c231c6656f182bed38df73f402d712691d59fef5f30d6b5a185980b91`.
- SHA del estado final de índices:
  `c071a1b0fbbb5dcb0ae0472a44d449b787edea50f8e5442b432820dc956afb42`.

La verificación independiente confirmó 16 `source_id` únicos, 20
`reference_id` únicos, asociaciones `source_ids` válidas, ningún ID externo al
manifiesto y exactamente 15 índices presentes con las definiciones aprobadas.

Hashes del catálogo aplicado:

- Sources:
  `47c18adb3e48111276a8b928c2fe605db8e901c397e53e6670d261dee11f44c2`.
- References:
  `055763a8349fbf7507e5b74a8d5f18381083f3f6fd79e313cd5eff01b3613b04`.
- Manifiesto:
  `a9c03aed2a585550f818e5e8bd31dcecfcd59ac978de8a988ebeb8bdd9cafcb2`.

## Invariantes legacy

Los valores live antes y después del apply fueron idénticos:

| Evidencia | SHA-256 antes/después |
| --- | --- |
| conteos | `fa804ce9e51cb081f433a131852c1ded34b131ba7d3465f7ad5c7f9877e9bcda` |
| documentos JSON legacy | `393de0ffae3438c0cfe4860a622bfa78a6f43a84e9e2e2dc5da2c29fabee731b` |
| identidad BSON | `8f211c188c9613100cb95ddeca3b6d374e4d7aad04689b85a9c4cbbec4feed76` |
| índices legacy | `ecd79c5c0df1b44ca8452e355c96922e5b5baaf343231332972c2312dbed3517` |
| agregado live | `293bf3a12e5e00d8689913bfb65de3e70c08695a5d5091526a53c8fc535479fc` |

Los hashes invariantes durable antes/después también coincidieron:

- collections:
  `d8cf8049d4833296bc84bee98e5eaa84e87c97d626b373d790c2b73569cfcf04`;
- indexes:
  `ecd79c5c0df1b44ca8452e355c96922e5b5baaf343231332972c2312dbed3517`;
- aggregate:
  `293bf3a12e5e00d8689913bfb65de3e70c08695a5d5091526a53c8fc535479fc`.

No se modificó, fusionó ni reidentificó ningún concepto.

## Segundo apply

Se ejecutó exactamente el mismo comando con el mismo ZIP, plan, decisiones,
backup y confirmaciones. Terminó con exit code 0 y stderr vacío.

- Outcome: `already_applied`.
- Sources creadas: 0; idénticas: 16.
- References creadas: 0; idénticas: 20.
- Mismo migration ID y manifiesto.
- Mismos hashes de entidades y timestamps.
- Índices nuevos: 0; presentes: 15.
- Legacy: idéntico al pre-apply.

## Export post-migración y round-trip

Export post-migración privado:

- `$XDG_STATE_HOME/mathmongo/s1c2p-20260712-qakHK9/`
  `mathkb_export_20260712_204612.zip`;
- modo 0600;
- tamaño 7,216,025 bytes;
- SHA-256:
  `43fe8553879b1778fbe2bb2661fa44601e8da4a750ea6258892f545681d5b508`;
- formato `mathkb_legacy_export` v1;
- 15 archivos media;
- conteos legacy anteriores más `sources=16`, `references=20` y
  `source_catalog_migration_manifest=1`;
- codec MongoDB Extended JSON v2 canónico declarado para las tres colecciones
  del catálogo.

La restauración se probó en
`MathV0_portability_validation_20260712_204756` con media aislada fuera del
directorio de datos real.

- Primera importación: 16 Sources, 20 References, 1 manifiesto y todos los
  documentos legacy insertados con sus IDs originales.
- Hashes de Sources, References, manifiesto, asociaciones y timestamps:
  idénticos a `MathV0`.
- Fingerprints de documentos JSON/BSON legacy y conteos: idénticos.
- Segunda importación: todos los documentos idénticos, cero inserts, cero
  duplicados, cero sobrescrituras y media sin cambios.
- Dos pruebas fake de contenido conflictivo confirmaron bloqueo antes de tocar
  legacy o media.
- La base temporal fue eliminada y se confirmó `present_after=false`.

Los índices no se serializan en el ZIP portable. Por ello una restauración bajo
otro nombre conserva documentos, catálogo e identidad, pero requiere
reinicializar sus índices operativos antes de comparar fingerprints de índices.
El manifiesto conserva `target_database=MathV0` como evidencia histórica y no es
reanudable contra el nombre temporal.

## Validación MathMongo read-only

Se inició Streamlit de forma controlada en loopback, puerto 8517, con `MathV0`
activa. Una sesión headless de Streamlit verificó:

- Catalog Status inicializado;
- 16 Sources visibles;
- 20 References totales en la verificación directa;
- `BottcherKarlovich1997`, `Python` e `IAIngenieria` visibles;
- Edit / Analyze Source abrió `BottcherKarlovich1997`;
- su sección References mostró 1 Reference;
- Concepts — Legacy Read Only mostró 51 conceptos exactos para esa Source;
- no aparecieron Sources fake/test/synthetic;
- Add Source renderizó sin enviar formularios;
- cero excepciones Streamlit.

El proceso temporal se detuvo ordenadamente y el puerto 8517 quedó libre.

## Validación de código

- Pruebas focales: 500 passed.
- Suite completa: 805 passed en 104.80 s.
- Regresiones de conflicto portable posteriores: 2 passed.
- `compileall`: correcto y sin bytecode en el checkout.
- Ruff diferencial: correcto.
- `git diff --check`: correcto.
- No reapareció `use_container_width=` en Python ejecutable.

## Limitaciones y recuperación

- La operación valida contenido MongoDB y media física; no implementa PDFs ni
  visor de PDFs.
- El ZIP portable no contiene definiciones de índices. Después de restaurar se
  debe inspeccionar Catalog Status y recrear explícitamente los índices
  aprobados.
- Para recuperación al estado pre-apply, conservar el backup pre-apply y
  verificar primero su SHA-256. Detener toda UI/escritura, preservar la base
  dañada para análisis y restaurar el ZIP únicamente en un `MathV0` exacto y
  físicamente vacío o en otra base controlada. No borrar ni reemplazar la base
  real sin una autorización humana nueva y un backup adicional.
- El backup pre-apply, export post-migración, decisiones y reportes permanecen
  privados fuera de Git.

No se hizo push y no se iniciaron fases P1, S2, S3 o S4.
