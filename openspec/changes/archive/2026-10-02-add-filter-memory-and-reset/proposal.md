# Proposal

## Why

The filter dialog (`AmcrFilterDialog`) is created from scratch every time
the user opens it, so every selection is lost after each download. Refining
a query ("same area, add one more period") means re-entering every picker
and date by hand. There is also no quick way back to the default state once
many filters are set (issue #84).

## What Changes

- The filter dialog remembers the last confirmed filters **per data type**
  (Fieldwork events, Sites, Individual finds) for the rest of the QGIS
  run. Reopening the dialog for the same data type restores all pickers,
  checkboxes and date ranges. Nothing is written to disk; after a QGIS
  restart (or a plugin reload) the dialog starts from the defaults again.
- State is remembered only when the dialog is confirmed with OK (after the
  existing date-range validation passes). *Cancel* leaves the remembered
  state unchanged.
- A new *Obnovit výchozí* button (`RestoreDefaults` role) in the button
  row resets the whole form to its **defaults**, not to an empty form:
  *Omezit vyhledávání rozsahem okna* checked, *PIAN – přesnost* with its
  three pre-selected levels, everything else empty. The reset is applied
  to the form only; the remembered state changes only on OK.
- When the dialog opens with restored filters that differ from the
  defaults, a notice at the top says so and how many filters are active,
  so a forgotten filter further down the scrollable form is not missed.
- Each picker gets a small clear button (✕) that returns that single
  filter to its **default** (empty for almost all pickers, the three
  pre-selected accuracy levels for *PIAN – přesnost*); it is available
  only while the filter differs from that default. "No PIAN
  restriction" is still reachable by unchecking all levels in the
  selection dialog.
- Restored codes that are no longer in the current codelists (after
  *Aktualizovat hesláře*) are dropped, and picker texts are rebuilt from
  the current codelist labels.
- README (section 3.3) and the v2.2.0 changelog entry in `metadata.txt`
  describe the new behaviour.

Out of scope:

- Persisting filters across QGIS restarts (`QgsSettings`) or in the QGIS
  project – considered in issue #84 as variants B and C, not chosen.
- Sharing filter values between data types.

## Capabilities

### New Capabilities

- `filter-dialog`: state of the filter dialog between openings – remembered
  filters per data type, reset to defaults, clearing a single filter and
  the notice about restored filters.

### Modified Capabilities

<!-- none – openspec/specs/ is not maintained (change-tracked) -->

## Impact

- Code: `amcr_viewer/amcr_dialog.py` (state capture/restore, defaults in
  one place, reset button, per-picker clear button, notice);
  `tests/smoke_test.py` (offline cases for restore, cancel, reset, clear
  and dropped codes). `amcr_viewer/amcr_viewer.py` is not expected to
  change – `run_download` keeps creating the dialog as today.
- No change to the digiarchiv API requests: `get_filters()`, `get_bbox()`
  and `get_komponenty()` keep their output for the same form state.
- No change to layer attributes or stored settings (`QSettings` is not
  touched).
- Target branch `version/v2.2.0` (unreleased): the change joins the v2.2.0
  changelog entry, no separate version bump.
- Qt5/Qt6 rules from `AGENTS.md` apply; no new dependencies.
