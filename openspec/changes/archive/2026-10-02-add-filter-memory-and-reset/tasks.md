# Tasks

## 1. Form state in one place

- [x] 1.1 In `amcr_viewer/amcr_dialog.py` add `DEFAULT_CODES` /
  `DEFAULT_CHECKS` and `_default_state()`; remove the hard-coded
  `pian_presnost` block from `setup_picker()` and apply the default
  through the new path. Verify: smoke test case "filtrační dialogy"
  still passes and a fresh `akce`/`lokalita` dialog still sends
  `f_pian_presnost` with the three codes (assert in the new test 1.4)
- [x] 1.2 Register pickers in `self.pickers` and add `_set_picker()`
  (cache + display text rebuilt from the current codelist, unknown codes
  dropped, clear-button state); route `open_dialog()` through it.
  Verify: `python3 tests/check_sources.py`, `ruff check .`
- [x] 1.3 Add `_snapshot()` / `_apply_state()` covering codes, checkboxes
  and date ranges (ISO strings or `None`; empty picker via `clear()`).
  Verify: smoke test round-trip – snapshot → apply on a fresh dialog →
  equal `get_filters()`, `get_bbox()`, `get_komponenty()`
- [x] 1.4 Extend `tests/smoke_test.py` with an offline case for 1.1–1.3
  (defaults incl. PIAN, round-trip for all three data types, unknown code
  dropped). Verify: smoke test passes in `qgis/qgis:ltr` and
  `qgis/qgis:stable`

## 2. Remember, reset, clear, notice

- [x] 2.1 Module-level `_REMEMBERED_STATE` keyed by `typ_dat`; store the
  snapshot in `accept()` after the date-range check, restore in the
  constructor. Verify (smoke test): OK → reopen restores; Cancel keeps
  the previous state; reversed range refused → state unchanged; another
  data type starts from defaults
- [x] 2.2 *Obnovit výchozí* button
  (`QDialogButtonBox.StandardButton.RestoreDefaults`, Czech text) that
  applies `_default_state()` to the form only. Verify (smoke test): reset
  + OK equals a fresh dialog; reset + Cancel keeps the remembered state
- [x] 2.3 `✕` button (`QToolButton`, tooltip *Vymazat výběr*, or
  *Vrátit výchozí výběr* for a picker with a non-empty default) per
  picker that returns that filter to its default, enabled only while it
  differs from the default. Verify (smoke test): clearing one picker
  removes only its key from `get_filters()`; the PIAN `✕` is disabled
  on a fresh dialog, enabled after a change and restores the three
  default levels
- [x] 2.4 Notice label at the top, shown only when a restored state
  differs from defaults, with the count of differing items; hidden on
  reset. Verify (smoke test): hidden for a fresh dialog and for a
  remembered default state, visible with the right count otherwise
- [x] 2.5 Reset `_REMEMBERED_STATE` between smoke-test cases (in
  `try/finally`) so cases stay independent; verify by running the smoke
  test twice in one container

## 3. Documentation and version

- [x] 3.1 README section 3.3: remembered filters per data type for the
  QGIS run, *Obnovit výchozí*, `✕` per filter, the notice; adjust the
  PIAN default note (reset restores it, `✕` clears it). Verify by reading
  the section against the spec
- [x] 3.2 Add bullets to the existing v2.2.0 entry of `changelog=` in
  `amcr_viewer/metadata.txt` (branch `version/v2.2.0` is unreleased, so
  no new version; `CITATION.cff` already says 2.2.0). Verify:
  `python3 tests/check_version_bump.py` (or the CI package job) passes

## 4. Final verification

- [x] 4.1 Run the AGENTS.md check set: `tests/check_sources.py`, bandit,
  detect-secrets `--all-files`, `flake8 --isolated amcr_viewer/`,
  `ruff check .`, `pyqgis4-checker` (log contains only the header), smoke
  test in `qgis/qgis:ltr` and `qgis/qgis:stable`; delete
  `amcr_viewer/__pycache__` afterwards
- [x] 4.2 `openspec validate add-filter-memory-and-reset --strict` passes
- [x] 4.3 Manual test in QGIS 3.44 and QGIS 4 (user): spec scenarios –
  reopen after a download, Cancel, reset + OK / Cancel, `✕` on one
  picker and on PIAN, notice text, separate state per data type,
  *Aktualizovat hesláře* between two openings, defaults after a QGIS
  restart
  - User: look and function verified on Fieldwork events, Sites and
    Individual finds; everything worked except two points – the notice
    started with an odd "ℹ" and `✕` on PIAN emptied it instead of
    restoring the default. Both fixed (commit d5e520d); the fix was
    re-tested by the user on Fieldwork events, for Sites and Individual
    finds it is covered by the smoke test.
- [x] 4.4 Archive before merge:
  `openspec archive add-filter-memory-and-reset --skip-specs` in the same
  PR
