# Tasks

## 1. Login-state check

- [x] 1.1 Add `_ensure_logged_in()` to `amcr_viewer/amcr_tools.py` per
  design.md (statuses `anonymous` / `logged_in` / `relogged` / `fallback` /
  `unknown`, `GET /api/user/islogged` with the current session, one re-login
  on `nologged`); verify with `python3 tests/check_sources.py` and
  `ruff check .`
- [x] 1.2 Add a comment to `_is_auth_error` that the current server never
  returns such an error on expiry and the check is kept as a fallback;
  verify by reading the diff
- [x] 1.3 Extend `tests/smoke_test.py` with offline cases using a fake
  session object (valid session, `nologged` + successful re-login,
  `nologged` + failed re-login, no credentials, network error); verify the
  smoke test passes in `qgis/qgis:ltr` and `qgis/qgis:stable`

## 2. Integration into the download

- [x] 2.1 Call `_ensure_logged_in()` in `load_amcr_data` after the
  re-entrancy guard, before the first query; on `fallback` push a message
  bar warning (Czech, scoped `Qgis.MessageLevel.Warning`) that the download
  runs anonymously and contains only access level A; verify by smoke test
  and code review
- [x] 2.2 Live check without credentials: anonymous download path sends no
  `islogged` request and a made-up `JSESSIONID` yields `nologged`
  (curl / probe script in scratch); verify outputs recorded in the PR
- [x] 2.3 Update `README.md` if it describes login/session behaviour; verify
  the text matches the new behaviour (or note that nothing needed changing)

## 2b. Logout when credentials are removed

- [x] 2b.1 Add `logout_from_api()` to `amcr_tools.py` and call it from
  `LoginDialog._forget_credentials`; extend the smoke test (session
  logged out + dropped, network error still drops it, no session = no
  request); update README and changelog; verify smoke test ltr + stable
- [x] 2b.2 Manual test in QGIS: log in, download, remove the stored
  credentials, download again; verify the log shows "Uživatel odhlášen"
  and the count drops to the anonymous one

## 3. Release preparation and verification

- [x] 3.1 Add changelog entries under v2.2.0 in `amcr_viewer/metadata.txt`
  (the fix ships with 2.2.0; `CITATION.cff` already says 2.2.0 and
  `date-released` moves on release day); verify both versions match
- [x] 3.2 Run the full local check set from `AGENTS.md` (check_sources,
  bandit, detect-secrets `--all-files`, flake8 `--isolated`, ruff,
  pyqgis4-checker log empty, smoke test ltr + stable); verify all clean
- [x] 3.3 Manual test in QGIS with a researcher account: download SN for
  whole CZ, simulate expiry in the Python console with
  `amcr_tools.AMCR_SESSION.get("https://digiarchiv.aiscr.cz/api/user/logout")`,
  download again; verify log shows re-login and the count matches the
  logged-in count (not the anonymous one)
