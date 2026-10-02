# Proposal

## Why

Digiarchiv changes its API without notice to clients. Issue #67 showed the
cost: digiarchiv v4.1.0 (Solr 10) changed the facet item shape from
`{"name": …}` to `[value, count]`, the plugin swallowed the resulting
exception and the person codelists (`vedouci`, `nalezce`) came out empty –
found by hand, after users were already affected. Today nothing in the
repository talks to the live API: `tests/smoke_test.py` is deliberately
offline and CI runs only on pull requests and pushes, so an API change is
noticed only when a user hits it.

## What Changes

- New scheduled GitHub Actions workflow `.github/workflows/api_monitor.yml`
  that runs once a day (and on manual dispatch) against the production
  digiarchiv and `api.aiscr.cz` OAI, without credentials.
- New **contract test** `tests/api_contract.py` (plain `requests`, no QGIS):
  sends the same requests the plugin sends and checks the shape of every
  response the plugin reads – endpoints, keys, value types, facet item
  shape, OAI sets, pagination, bbox restriction, PIAN geometry, filters,
  login error path. Says *what* changed in the API.
- New **live plugin test** `tests/api_plugin_live.py`, run in
  `qgis/qgis:ltr`: calls the plugin's own functions (`fetch_set` for every
  codelist set, `load_translations`, `load_amcr_data` per data type) against
  the live API and checks that they produce non-empty, well-formed results.
  Says *whether* the change breaks users.
- Every run records the deployed digiarchiv version (git-describe string
  from the web bundle) in its summary.
- Outages (timeouts, HTTP 5xx, connection errors after retries) are
  reported as *unavailable*, separately from contract breaks, and do not
  open an issue.
- A failing or drifting run opens **one** tracking issue (label
  `api-monitor`) or updates the open one; the next clean run closes it.
- `AGENTS.md` documents the monitor (what it runs, how to run it locally,
  how to read the issue).

What changes for a plugin user: nothing directly – no file under
`amcr_viewer/` changes and the plugin version is not bumped. Indirectly,
API breaks like #67 are found within a day of a digiarchiv release instead
of by users.

Out of scope:

- Logged-in checks (variant D): no account secret is stored in the repo;
  anonymous runs cover only `pristupnost=A` records.
- Testing version branches on schedule: GitHub runs `schedule` only on the
  default branch; other refs can be run by manual dispatch.
- Availability monitoring of digiarchiv as a service.

## Capabilities

### New Capabilities

- `api-monitoring`: periodic verification that the digiarchiv / AMČR OAI
  API still satisfies the contract the plugin depends on, and reporting of
  breaks through a tracking issue.

### Modified Capabilities

<!-- none – openspec/specs/ is not maintained (change-tracked) -->

## Impact

- New files: `.github/workflows/api_monitor.yml`, `tests/api_contract.py`,
  `tests/api_plugin_live.py`; edited `AGENTS.md`.
- Affected plugin modules (read, not changed): `amcr_viewer/amcr_tools.py`
  (`load_translations`, `load_amcr_data`, `login_to_api`),
  `amcr_viewer/amcr_codelists.py` (`slovnicek`, `fetch_set`).
- API: one run ≈ a few dozen anonymous requests to
  `digiarchiv.aiscr.cz/api/*` and `api.aiscr.cz/2.2/oai`, restricted to a
  small bbox – negligible load for digiarchiv.
- GitHub: scheduled workflow minutes (two short jobs per day), the
  `api-monitor` label, `issues: write` permission for the reporting job
  only. Depends on the digiarchiv repository
  (`ARUP-CAS/aiscr-digiarchiv-2`) only as the source of the API under test.
- PR targets `main` (repository tooling, no plugin behaviour change).
