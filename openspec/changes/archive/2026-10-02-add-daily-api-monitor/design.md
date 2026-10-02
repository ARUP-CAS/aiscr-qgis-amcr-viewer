# Design

## Context

- What broke in #67: the facet item shape of `api/search/query`
  (`json.nl` `arrntv` → `arrarr` with the Solr 10 migration in digiarchiv
  v4.1.0). `fetch_set` caught the `TypeError`, logged a warning and returned
  `[]`; nothing outside QGIS noticed. The plugin now accepts both shapes
  (`amcr_codelists._facet_name`) and keeps previous codelist values when a
  set comes back empty, which makes the next break of this kind even
  quieter for users – only a check outside the plugin catches it.
- What the plugin uses (from the code on `main`):
  - `GET https://digiarchiv.aiscr.cz/api/assets/i18n/cs.json`
    (`amcr_tools.load_translations`)
  - `GET …/api/search/query` with `entity`, `mapa=true`, `sort=ident_cely
    asc`, `rows=500`, `page`, `loc_rpt=minLat,minLon,maxLat,maxLon`,
    filters as `key=value:or` lists, date ranges; response
    `response.numFound` / `response.docs[]`, errors as HTTP 200 without
    `response` (`amcr_tools.load_amcr_data`, `_api_get_json`)
  - PIAN geometry requests in batches (`amcr_tools.load_amcr_data`)
  - `…/api/search/query` with `rows=0&noFacets=false&onlyFacets=true`,
    response `facet_counts.facet_fields.<f_…>[]` (`amcr_codelists.fetch_set`
    for `vedouci`, `nalezce`)
  - `GET https://api.aiscr.cz/2.2/oai?verb=ListRecords&metadataPrefix=oai_dc
    &set=…` with `resumptionToken` pagination (`fetch_set`, all other sets
    in `amcr_codelists.slovnicek`)
  - `POST …/api/user/login`, `GET …/api/user/islogged`, `…/logout`
    (`amcr_tools.login_to_api`, session check)
- Live probe (2026-10-02, anonymous, Praha bbox `49.9,14.3,50.2,14.7`, one
  page of 500): `akce` numFound 20 635 (1.0 MB, 0.6 s), `lokalita` 342
  (0.8 MB, 0.4 s), `pian` 30 321 (0.8 MB, 0.5 s), `samostatny_nalez` 0
  (anonymous SN are sparse – the test bbox must be chosen so that every
  entity returns records). Bbox chosen: Mikulov `48.8,16.6,48.9,16.75`
  – akce 185, lokalita 18, samostatny_nalez 2, pian 294. Only 12
  anonymous map-enabled SN exist in the whole CZ, so 2 is accepted:
  archive records do not disappear (maintainer decision); facet request 54 fields, items are lists. The
  deployed version read from the web bundle: `v4.0.3-237-g96deec70-dirty`
  (footer text is hard-coded and not reliable).
- GitHub runs `schedule` only on the default branch (`main`) and disables
  scheduled workflows after 60 days without repository activity.

## Goals / Non-Goals

**Goals:**
- Daily, credential-free check that tells apart three outcomes: the API
  changed in a way the plugin breaks on (fail), the API changed in a way
  the plugin survives (drift), the API was not reachable (unavailable).
- Messages specific enough to start a fix without re-probing (field, old
  shape, new shape, request).
- One tracking issue, no daily noise.

**Non-Goals:**
- Logged-in access, access levels B–D.
- Full data validation (counts, contents of records).
- Changing plugin code to make it more testable – if a function cannot be
  called without UI, the live test provides a fake `iface` / canvas.

## Decisions

1. **Two scripts, two jobs.** `tests/api_contract.py` (job *API contract*,
   `ubuntu-latest` + `actions/setup-python`, `requests` pinned in workflow
   `env`) and `tests/api_plugin_live.py` (job *Plugin against live API*,
   `docker run qgis/qgis:ltr`, same invocation style as the smoke test).
   *Alternative:* one script in the QGIS container – rejected: a QGIS image
   problem would hide the contract result, and the contract check would
   pay the image pull every day.
   Only `ltr` for the live job: the API path does not differ between Qt5
   and Qt6, which the PR smoke test already covers on both.
2. **Contract = recorded expectations in the script, not a stored
   baseline file.** Each check states the expected keys/types/shapes
   inline (e.g. facet item is `[str, int]`, `numFound` is `int`,
   `docs[].ident_cely` is `str`). A mismatch the plugin tolerates is
   reported as **DRIFT** (e.g. facet shape back to `{"name":…}`, an
   extra type the parser accepts), a mismatch it does not tolerate as
   **FAIL**. Updating an expectation is a reviewed code change.
   *Alternative:* snapshot JSON baseline refreshed automatically – rejected:
   a silent baseline refresh would accept the very change we want to see.
3. **Statuses and exit codes.** Each check yields `OK` / `DRIFT` / `FAIL` /
   `UNAVAILABLE` + detail. Both scripts write `results-<job>.json`
   (check name, status, detail, request URL without secrets) and a Markdown
   table to `$GITHUB_STEP_SUMMARY` when set; exit code 1 on any `FAIL` or
   `DRIFT`, 0 otherwise (an all-`UNAVAILABLE` run is green but visible in
   the summary). Locally the scripts print the same table.
4. **Retries.** Network errors, timeouts and HTTP 5xx: 3 attempts with
   backoff (2 s, 8 s). After that the check is `UNAVAILABLE`; checks that
   depend on it are skipped as `UNAVAILABLE`, not `FAIL`. HTTP 4xx or a
   200 with an `error` body is a real answer and is judged by the contract.
   A per-host circuit breaker follows: once a host fails its full retry
   cycle, later requests to it return "unreachable" without network I/O,
   so an all-unreachable run ends in ~10 s instead of tens of minutes.
5. **Test inputs from the live API, not from `heslar.csv`.** Filter values
   are taken from facets of the same bbox in the same run; the test bbox is
   a fixed small area where every entity (`akce`, `lokalita`,
   `samostatny_nalez`, `pian`) returns a non-zero anonymous count below
   one page, chosen during implementation by a probe and documented in
   the script. Pagination is checked separately with `rows=100` on a larger
   area (pages must not overlap; downloaded ≥ numFound when it is small
   enough).
6. **Live plugin test thresholds.** For each set in
   `amcr_codelists.slovnicek`: `fetch_set` must return ≥ 1 item **and** at
   least 50 % of the row count of that category in the bundled
   `codelists/heslar.csv` (a shrunken codelist is the #67 symptom). For
   each data type: `load_amcr_data` on the test bbox (fake `iface`, fake
   canvas in EPSG:5514) must add at least one layer with ≥ 1 feature with
   a valid geometry and the expected attribute fields. The plugin package
   is imported as a package (`amcr_viewer.amcr_tools`), so its relative
   imports work – a bare `spec_from_file_location` makes `load_amcr_data`
   swallow the import error into "0 records".
7. **Deployed version.** Fetch `https://digiarchiv.aiscr.cz/home`, scan the
   referenced `*.js` bundles for `raw:"v…"` (git-describe) and report it;
   not finding it is a `DRIFT` of its own check, never a `FAIL` of the run.
8. **Reporting job** (`needs` both, `if: always()`, only when
   `github.ref_name == github.event.repository.default_branch`; the
   workflow has no other triggers than `schedule` and `workflow_dispatch`; `permissions: issues: write`
   for this job only, `contents: read` elsewhere). It downloads both result
   files (artifacts) and with `gh`:
   - any `FAIL`/`DRIFT` → find the open issue with label `api-monitor`; if
     none, create it (`gh label create api-monitor --force` first); if it
     exists and the fingerprint (sorted names of FAIL/DRIFT checks – not
     UNAVAILABLE, which would make it flap – stored as an HTML comment in
     the issue body) differs, add a comment and update the
     fingerprint; identical fingerprint → do nothing;
   - every check `OK` → close the open issue with a comment linking the
     run;
   - no `FAIL`/`DRIFT` but some `UNAVAILABLE` → leave the issue as it is
     (an outage proves neither break nor recovery);
   - a job that did not produce its result file (crashed script, image
     pull failure) counts as one `FAIL` check named after the job.
   Issue text in Czech (repo convention for issues), unwrapped GFM: deployed
   version, table of non-OK checks, run link, how to reproduce locally.
   *Alternative:* `actions/github-script` or a marketplace action – rejected:
   `gh` is preinstalled and needs no third-party action pin.
9. **Schedule** `cron: "17 5 * * *"` (07:17 CEST) – off the full hour,
   before the working day. Plus `workflow_dispatch`. Concurrency group per
   ref, `cancel-in-progress: false`.
10. **Not a PR check.** The new workflow does not run on `pull_request`: a
    PR must not go red because digiarchiv is down. Contributors run the
    scripts locally or dispatch the workflow on their branch.

## Risks / Trade-offs

- **False alarms from data changes** (a record deleted in the test bbox,
  an entity count dropping to 0) → thresholds are "≥ 1" and "≥ 50 % of the
  bundled codelist", not exact counts; the bbox is chosen with margin.
- **Scheduled workflow auto-disabled after 60 days of inactivity** →
  documented in `AGENTS.md`; any push to `main` (dependabot included)
  resets the timer.
- **Tests only `main`'s plugin code** – a fix waiting on a version branch
  is not exercised by the schedule → manual dispatch on that branch.
- **Anonymous only** → `pristupnost` B–D paths and login success are not
  covered; the login *error* path is.
- **Load on digiarchiv** – a few dozen small requests a day; negligible.

## Verification

- Both scripts run locally against the live API and pass
  (`uv run -q --no-project --with requests python tests/api_contract.py`;
  live test in `docker run qgis/qgis:ltr`).
- **#67 regression check**: run the live test against the plugin as of the
  commit before the #67 fix (`git archive`) – it must FAIL on `vedouci` /
  `nalezce`; the contract test must flag a facet-shape DRIFT when its
  expectation is temporarily set to the old `{"name":…}` shape.
- Outage simulation: point the scripts at an unroutable host
  (environment override of the base URLs) → all checks `UNAVAILABLE`,
  exit 0.
- Reporting logic tested with a dry-run mode (`API_MONITOR_DRY_RUN=1`
  prints the `gh` commands instead of running them) for: new issue, same
  fingerprint, changed fingerprint, recovery.
- The full `AGENTS.md` check set passes on the new files (check_sources,
  bandit, detect-secrets `--all-files`, flake8 `--isolated` on
  `amcr_viewer/`, ruff on the repo); `actionlint` on the new workflow.
- After merge: one manual `workflow_dispatch` on `main` and inspection of
  the summary.
