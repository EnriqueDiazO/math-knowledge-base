# Legacy Curves migration audit — 2026-07-28

## Authority

- Migration ID: `2026_07_28_canonicalize_bottcher_karlovich_curve_links`
- Migration checksum: `43ed779ebfaaf7a0b27fc502cb743f9bd97143e8cb2975a15990c75aa4c895e4`
- Registry checksum: `e8044feec0ea3aa497ee54803e06da0feb77dea22e322911673127ae87104c0c`
- Source ZIP SHA-256:
  `2b3f1cd0c6fe88dd5999a4b89fa8bcf2cfa3880cf2df379eb1891c0051e8355e`
- Applied at: `2026-07-28T17:53:52.710Z`

The exact registry maps each approved historical identity to itself. No fuzzy
matching or inferred replacement is used.

## Verified raw backup

- Directory:
  `~/.local/share/mathmongo/backups/legacy-link-migration/20260728T175350Z/`
- Aggregate SHA-256:
  `8e5db3476ddbb93dd8ebfb57f9068d3a50001d18188b6b61838639c52336652f`
- Inventory: 19 collections and 53 documents.
- Every raw dump file has a SHA-256 entry in `verification.json`.
- Restore result: collection inventory and counts matched `MathV0` exactly.
- The unique temporary verification database was dropped and confirmed absent.

An earlier dump at `20260728T175310Z` was retained but was not accepted as
backup evidence: restore verification failed before any `MathV0` write.

## Applied changes

- Restored exactly two checksum-approved Concept documents:
  `id_Curves_001@BottcherKarlovich1997` and
  `id_Curves_002@BottcherKarlovich1997`.
- Matched and post-validated exactly the six approved Evidence Link IDs.
- Rewrote zero Evidence Link documents because their stored exact identities
  already equal the canonical identities.
- Inserted exactly one applied migration marker, after all postconditions.
- No Concept, Evidence Link, or migration marker was duplicated.

An independent post-migration restore comparison found all documents in the 18
unrelated/pre-existing collection projections byte-semantically unchanged.
The six Evidence Link documents were also unchanged.

## Postconditions

- Each of the six Evidence Links resolves to exactly one Concept.
- Structured portability issues changed from 6 to 0.
- The migration marker exists exactly once.
- A second migration execution was a no-op with zero modified documents.
- Application export succeeded and its ZIP inspection passed:
  `mathkb_export_20260728_180100.zip`, format version 1, SHA-256
  `b2deb6258093e8f1853dfa802ce977191cce697c4bb0a138c2fa59505ebbf3f0`.
- Database Update preview of the incoming ZIP reports zero invalid documents,
  zero legacy-link blockers, and is eligible to apply.
- The full Database Update was not executed.

## Validation

- Focused migration/import/export/update tests: passed.
- Ruff on every modified Python file: passed.
- `git diff --check`: passed.
- Full suite: 1563 passed, 53 skipped; four failures are identical pre-existing
  `HEAD` failures (three legacy datetime mocks and one static mutable-path guard).
