# Design

## Context

See proposal.md – Why. Current state of `amcr_viewer/amcr_dialog.py`
(branch `version/v2.2.0`):

- `AmcrViewer.run_download()` builds a new `AmcrFilterDialog(typ_dat)` for
  every opening (`amcr_viewer.py`), without a parent.
- Form state is spread over:
  - `self.selection_cache` – 19 keys, each a list of codelist codes; the
    picker's read-only `QLineEdit` text is only set inside the nested
    `open_dialog()` closure in `setup_picker()`, which keeps no reference
    to the line edit.
  - checkboxes `chk_bbox` (default checked), `chk_posevidence`,
    `chk_proj_akce` (events only), `chk_komponenty` (events and sites);
  - `self.date_ranges` – `(api_field, name, date_from, date_to)` with
    nullable `QgsDateEdit`s (`clear()` is the only correct way to empty
    them, see `_date_edit`).
- The one non-empty default, *PIAN – přesnost* = `HES-000861/862/863`, is
  hard-coded inside `setup_picker()` together with its display text.
- Codelists are module-level dicts in `amcr_codelists.py` mapping
  **label → code**; `refresh_globals()` updates them in place after
  *Aktualizovat hesláře*, so the dialog always sees the current values.
- `tests/smoke_test.py` already builds the dialog offscreen for all three
  data types and checks `get_filters()` for date ranges.

## Goals / Non-Goals

**Goals:**

- One snapshot format that describes the whole form, used for remember,
  restore, defaults and "is it default?" comparison.
- No change in `get_filters()` / `get_bbox()` / `get_komponenty()` output
  for the same form state.

**Non-Goals:**

- Persisting to `QgsSettings` or the project (variants B and C of #84).
- Remembering the window size or scroll position.

## Decisions

### Snapshot = plain dict kept at module level in `amcr_dialog.py`

`_REMEMBERED_STATE: dict[str, dict]` keyed by `typ_dat`. The snapshot is

```python
{
    "codes": {cache_key: [code, ...], ...},   # only pickers of this typ
    "checks": {"bbox": bool, "posevidence": bool, ...},
    "dates": {api_field: (iso_from | None, iso_to | None), ...},
}
```

Dates are stored as ISO strings (or `None` for an empty picker), never as
`QDate`, so a stored value can never turn an empty picker into "today".

- *Why module level, not on `AmcrViewer`:* `run_download()` stays
  untouched and the smoke test can exercise remember/restore just by
  creating dialogs. QGIS (and Plugin Reloader) re-imports the plugin
  package on reload, which drops the dict – that matches the "QGIS run
  only" requirement.
- *Alternative – keep one dialog instance per type and only `hide()` it:*
  rejected. Restoring would be free, but Cancel would then keep the
  cancelled edits (the requirement says it must not), and long-lived
  dialogs would hold stale codelist references after an update.
- *Alternative – pass state in/out through `AmcrViewer`:* works, but adds
  plumbing in two files for no behavioural gain.

### Defaults defined once

A module-level `DEFAULT_CODES = {"pian_presnost": ["HES-000861",
"HES-000862", "HES-000863"]}` and `DEFAULT_CHECKS = {"bbox": True}`
replace the hard-coded block in `setup_picker()`. `_default_state()`
builds a full snapshot for the dialog's `typ_dat` from them. It is used
by the constructor (no remembered state), the reset button and the
"differs from defaults" comparison – one definition, three users.

### Pickers keep a handle to their widgets

`setup_picker()` registers each picker in `self.pickers[cache_key] =
(data_source, display_field, clear_btn)`. A single
`_set_picker(cache_key, codes)` sets `selection_cache`, rebuilds the
display text from the current codelist (inverted `code → label`, sorted
like the selection dialog), drops unknown codes and enables/disables the
clear button. `open_dialog()`, restore, reset and clear all go through
it, so the display text can never disagree with the cache.

Display text is rebuilt from codes rather than stored, so a label renamed
by a codelist update shows its new name, and a removed code disappears
(spec: *Restored values follow the current codelists*).

### Remember only in `accept()` after validation

`accept()` already returns early on a reversed date range; the snapshot is
taken just before `super().accept()`. `reject()` is not overridden.

### Reset button

`QDialogButtonBox.StandardButton.RestoreDefaults` with Czech text
*Obnovit výchozí* (the standard button would otherwise show the Qt
translation of "Restore Defaults", which depends on the installed Qt
translations). Clicking applies `_default_state()` to the form and hides
the notice; `_REMEMBERED_STATE` is untouched until OK.

The button box already holds *Aktualizovat hesláře* in `ActionRole`; the
reset button sits next to it on the left, OK/Cancel stay on the right.

### Per-picker clear button

A narrow `QToolButton` with text `✕` and tooltip *Vymazat výběr* next to
*Vybrat…*. It calls `_set_picker(cache_key, [])`. For
`pian_presnost`, empty means the filter is not sent (current
`get_filters()` behaviour for an empty list) – this matches the spec.

Checkboxes and date pickers do not get their own clear button: a
checkbox is one click, and `QgsDateEdit` with `setAllowNull(True)`
already has its own clear control.

### Notice about restored filters

A `QLabel` above the bbox checkbox, styled like the existing component
warning (neutral info colours), hidden by default. Shown in the
constructor only when a remembered state exists **and** differs from
`_default_state()`. Text: *Načteny filtry z minulého hledání (aktivní
filtry: N).* N counts form items that differ from the default – one per
picker, checkbox and date row (a date row counts once even with both
bounds set). Hidden again on reset; not updated live on every edit (it
describes what was loaded, not the current form).

### Qt5/Qt6

`QToolButton` from `qgis.PyQt.QtWidgets`; all enums fully scoped
(`QDialogButtonBox.StandardButton.RestoreDefaults`,
`QDialogButtonBox.ButtonRole.ResetRole`); no `exec_()`.

## Risks / Trade-offs

- [Forgotten filter gives a suspiciously small result] → notice at the top
  with a count; reset is one click.
- [Restored bbox restriction with a different map extent] → bbox is a
  checkbox, the extent itself is read at download time as today; nothing
  extent-specific is stored.
- [Codelist update removes a selected code] → dropped silently on
  restore. Considered warning about it; not done, because the picker text
  already shows what is selected and the case is rare.
- [Plugin reload during development keeps the old dict] → only if the
  package is not re-imported; both QGIS and Plugin Reloader do re-import.

## Verification

- Smoke test (offline, `qgis/qgis:ltr` and `qgis/qgis:stable`): OK →
  reopen restores codes/checks/dates and `get_filters()` is equal; Cancel
  keeps the previous state; reset + OK equals a fresh dialog; clear drops
  one key from `get_filters()`; unknown code is dropped; notice visible
  only for non-default state; types do not share state.
- Manual test in QGIS 3.44 and QGIS 4: the scenarios from the spec, plus
  *Aktualizovat hesláře* between two openings.
