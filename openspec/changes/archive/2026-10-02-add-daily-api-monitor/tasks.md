# Tasks

## 1. Contract test

- [x] 1.1 Probe and fix the test inputs: a small bbox where `akce`,
  `lokalita`, `samostatny_nalez` and `pian` all return 1–499 anonymous
  records, and a larger area for pagination; record the probe numbers in
  the script header; verify by a probe run in scratch
- [x] 1.2 Write `tests/api_contract.py` with the status model, retries and
  outputs from design.md (decisions 3, 4, 7) and checks for: i18n
  `cs.json`, every OAI set in `amcr_codelists.slovnicek` (first page shape
  + `resumptionToken` paging), facet fields `f_vedouci` / `f_nalezce` item
  shape, main query per entity (keys and value types the plugin reads,
  `numFound` int), pagination without overlap, bbox restriction, PIAN
  batch geometry, every filter key the dialog builds (values taken from
  live facets), date range, error answer for an invalid parameter (HTTP 200
  without `response`), unknown entity, login with deliberately wrong
  credentials; verify a local run is all OK
- [x] 1.3 Verify the drift detection: temporarily set the facet
  expectation to the old `{"name":…}` shape → DRIFT reported with the
  field and both shapes; revert

## 2. Live plugin test

- [x] 2.1 Write `tests/api_plugin_live.py` (package import of
  `amcr_viewer`, fake `iface` / canvas, thresholds from design.md
  decision 6, same status model and outputs); verify it passes in
  `qgis/qgis:ltr`
- [x] 2.2 #67 regression: run it against the plugin from the commit before
  the #67 fix (`git archive` into scratch) → FAIL on `vedouci` and
  `nalezce`; verify and record the output

## 3. Workflow and reporting

- [x] 3.1 Write `.github/workflows/api_monitor.yml` per design.md
  (decisions 1, 8, 9, 10): pinned action SHAs as in `code_quality.yml`,
  pinned `requests`, artifacts with result files, reporting job with
  `issues: write` only; verify with `actionlint`
- [x] 3.2 Reporting script (inline step or `tests/api_monitor_report.py`)
  with `API_MONITOR_DRY_RUN=1`; verify the four cases (new issue, same
  fingerprint, changed fingerprint, recovery) and that a run with only
  UNAVAILABLE leaves the issue untouched
- [x] 3.3 Outage simulation (unroutable base URL override) → all
  UNAVAILABLE, exit 0; verify

## 4. Documentation and checks

- [x] 4.1 `AGENTS.md`: new subsection on the API monitor (what it runs,
  local commands, how to read the issue, 60-day schedule disable, manual
  dispatch for version branches); verify by reading the diff
- [x] 4.2 Run the `AGENTS.md` check set (check_sources, bandit,
  detect-secrets `--all-files`, flake8 `--isolated` on `amcr_viewer/`,
  ruff, smoke test in `qgis/qgis:ltr` and `:stable` – unchanged plugin
  code, must stay green) and `openspec validate add-daily-api-monitor
  --strict`; verify all clean
- [x] 4.3 After merge into `main`: manual `workflow_dispatch` on `main`,
  inspect the summary and that no issue was opened on a clean run
  - Run 37059874538 on `main` (02144d8), 2026-10-02: not a clean run –
    `api.aiscr.cz/2.2/oai` returns `amcr:amcr` for `metadataPrefix=oai_dc`
    since that evening (`2.0`/`2.1` correct). Contract job FAIL on all 17
    OAI sets, live job FAIL on all 17 OAI `fetch_set`; digiarchiv facets
    and downloads OK. Report opened issue #89 with label `api-monitor`,
    deployed version, 34 failing checks and run link; run ended red as
    designed. The clean-run path (no issue / issue closed) was verified
    by the dry run in 3.2 and waits for the API fix.
