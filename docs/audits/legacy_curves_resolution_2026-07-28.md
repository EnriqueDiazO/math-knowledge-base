# Legacy Curves resolution audit — 2026-07-28

## Scope and safety

This audit used read-only MongoDB queries, ZIP reads, hashes, Git history, and
generated-export metadata. It performed no MongoDB writes and records no
mathematical body content.

## Live MathV0 observations

For both `(id_Curves_001, BottcherKarlovich1997)` and
`(id_Curves_002, BottcherKarlovich1997)`, the live read-only audit found:

- zero exact `id` plus `source` matches;
- zero same-`id` candidates;
- zero exact alias candidates;
- zero Concepts using the historical `source`;
- zero Relations using either historical endpoint.

The Source Catalog contains the exact historical Source name as
`src_c9502cbb-2fe9-4552-ad45-9f066d707e9b`, with Reference
`ref_fb9c664c-0e55-4311-8c41-166c067e1bad`. Those catalog records corroborate
the source identity but are not, by themselves, Concept replacements.

## Exact historical recovery

The newest available update export is
`mathkb_export_20260728_144625.zip`, SHA-256
`2b3f1cd0c6fe88dd5999a4b89fa8bcf2cfa3880cf2df379eb1891c0051e8355e`.
Its metadata identifies `MathV0`, contains all six expected Evidence Link IDs,
and contains exactly one historical Concept for each target identity.

| Legacy identity | Result | `_id` | Title | Type | Concept SHA-256 |
|---|---|---|---|---|---|
| `id_Curves_001@BottcherKarlovich1997` | `restore_exact_legacy` | `696d3910ad8e62d930281bf5` | Arco en el plano complejo | `definicion` | `2ea479796f9afedccc726defe4cfa4bab3ca2ee9434ac86bc91ee10e37dd7eb3` |
| `id_Curves_002@BottcherKarlovich1997` | `restore_exact_legacy` | `6972f569106d300838b4eb2d` | Caracterización topológica de los arcos en el plano complejo | `proposicion` | `971b2413bd9c9ccb012c91856b8e1da6b0976af79865cd6512570132008f158a` |

Both recovered documents have no legacy aliases. They share the same exact
Reference digest
`2555fc91560b39aa0af26b780ddeedd71465b477369bc61adaffe326d229a253`.
Their Concept-body hashes match their paired historical `latex_documents`
body hashes. The ZIP also contains four Relations using the two exact
historical endpoints.

The same `_id`, identity, title, type, Reference digest, content digest, and
creation/update dates occur unchanged in exports from 2026-03-09, 2026-07-09,
2026-07-18, and 2026-07-28. Generated TeX exports independently retain both
exact `id@source` identities.

## Decision

No distinct current canonical replacement is structurally demonstrated.
Both identities are therefore resolved as `restore_exact_legacy`, using the
exact recovered documents and their original MongoDB `_id` values. The
canonical registry maps each recovered identity to itself; no fuzzy, title-only,
or inferred remapping is authorized.
