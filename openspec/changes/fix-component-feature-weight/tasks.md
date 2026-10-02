# Tasks

## 1. Weight computed from passing components

- [x] 1.1 In `amcr_viewer/amcr_tools.py` extract the per-component entry
  building of the *Načíst komponenty* branch into a pure helper that takes
  the DJ metadata, the component list and a pass predicate, filters first
  and sets `vaha = 1/len(passing)`; set `vaha = 1` explicitly for a DJ
  without components; verify with `python3 tests/check_sources.py`,
  `flake8 --isolated amcr_viewer/` and `ruff check .`
- [x] 1.2 Extend `tests/smoke_test.py` with an offline case for the helper
  (4 components no filter → 4×0.25; 1 of 4 passes → 1.0; 2 of 3 pass →
  2×0.5, sum 1 within tolerance; no components → 1 entry, weight 1);
  verify the smoke test passes in `qgis/qgis:ltr` and `qgis/qgis:stable`

## 2. Documentation

- [x] 2.1 Add `prvek_vaha` (alias *Váha prvku*) to the component fields
  table in `README.md` with the rule "1/n, n = features created from the
  same documentation unit after filters"; verify by reading the rendered
  table
- [x] 2.2 Extend the v2.2.0 changelog bullet about the feature weight in
  `amcr_viewer/metadata.txt` (weights of one documentation unit sum to 1
  also with period/area filters); no version bump – 2.2.0 is unreleased and
  `CITATION.cff` already says 2.2.0; verify both versions match

## 3. Verification

- [x] 3.1 Run the full local check set from `AGENTS.md` (check_sources,
  bandit, detect-secrets `--all-files`, flake8 `--isolated`, ruff,
  pyqgis4-checker log empty, smoke test ltr + stable); verify all clean
- [ ] 3.2 Manual test in QGIS (user): akce in a small window with *Načíst
  komponenty* and one period filter; verify in the attribute table that
  `prvek_vaha` sums to 1 per `dj_id`
