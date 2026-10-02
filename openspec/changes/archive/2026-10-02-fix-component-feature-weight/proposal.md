## Why

Issue #55 added the `prvek_vaha` (feature weight) attribute: when *Načíst
komponenty* is on, every component of a documentation unit (DJ) becomes its
own feature on the same PIAN geometry, and the weight 1/*n* lets spatial
analyses count the geometry once. The unreleased implementation on
`version/v2.2.0` takes *n* from **all** components of the DJ, before the
period/area filter. With a component filter active the weights of one DJ no
longer sum to 1 (DJ with 4 components, 1 passes the Neolithic filter → one
feature with weight 0.25 instead of 1), so weighted counts are wrong exactly
when users filter. See the comment on #55.

## What Changes

- *n* in `prvek_vaha = 1/n` is the number of component features actually
  created for the DJ, i.e. components that pass the period/area filters.
- The weights of all features created from one DJ sum to 1 with or without
  filters.
- A DJ without components keeps its single feature with weight 1 (today the
  value comes from a default; it becomes explicit).
- `README.md` documents `prvek_vaha` in the component fields table (it is
  missing there today).
- Changelog entry under v2.2.0 in `amcr_viewer/metadata.txt` is extended
  (the feature is unreleased, no separate version bump).

## Capabilities

### New Capabilities
- `component-features`: one feature per component of a fieldwork event or
  site, and the weight attribute that de-duplicates shared geometries.

### Modified Capabilities

## Impact

- `amcr_viewer/amcr_tools.py` – component feature creation in
  `load_amcr_data` (section B, attribute parsing).
- `tests/smoke_test.py` – offline check of the weights.
- `README.md`, `amcr_viewer/metadata.txt` (changelog only).
- No change to the digiarchiv API contract, layer schema or stored settings.
- `filter-components-via-component-endpoint` (#70) changes how components
  are selected; it builds on this change and must keep the weight rule.
