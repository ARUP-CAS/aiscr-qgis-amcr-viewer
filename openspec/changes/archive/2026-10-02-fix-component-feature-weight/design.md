## Context

`load_amcr_data` in `amcr_viewer/amcr_tools.py` (section B) builds, for each
DJ with a PIAN and *Načíst komponenty* on, one metadata dict per component
and appends it to `pian_lookup[pian_id]`. The weight is set as
`'vaha': 1/komps_count` with `komps_count = len(komps)` computed **before**
the loop that skips components failing `komp_projde_filtrem`. The empty-DJ
branch leaves `vaha` out and the feature builder falls back to
`meta.get('vaha', 1)`.

## Goals / Non-Goals

**Goals:** weights of one DJ sum to 1 under any filter; the rule is
testable offline.

**Non-Goals:** weighting across DJs or across records that share one PIAN
(a PIAN shared by several DJs still yields several features – the weight
only de-duplicates components of one DJ, as #55 asked); changing the layer
schema.

## Decisions

1. **Filter first, then weigh.** Build the list of passing components, then
   set `vaha = 1/len(passing)`. Alternative – a second counting pass with
   `sum(komp_projde_filtrem(...))` – duplicates the filter call and drifts
   if the filter changes (#70 replaces it).
2. **Extract a small pure helper** (e.g. `_component_entries(dj_meta, komps,
   passes)` returning the list of per-component dicts with `vaha`, where
   `passes` is a predicate) so the smoke test can check weights without
   QGIS layers or network. The helper must not depend on how components are
   selected, so #70 can pass a different predicate.
3. **Explicit weight 1 for a DJ without components** instead of relying on
   the `meta.get('vaha', 1)` default – the default stays as a safety net.

## Risks / Trade-offs

- Floating-point: 1/3 weights sum to 0.999…; acceptable for analyses,
  test with a tolerance.
- The helper extraction touches a long function; keep the diff limited to
  the component branch.

## Verification

- Smoke test cases: 4 components no filter → 4×0.25; filter keeps 1 of 4 →
  weight 1; keeps 2 of 3 → 2×0.5; no components → 1 entry, weight 1.
- Full AGENTS.md check set (ltr + stable smoke test, pyqgis4-checker).
- Manual QGIS test by the user: download akce with *Načíst komponenty* and
  a period filter, check in the attribute table that `prvek_vaha` sums to 1
  per `dj_id`.
