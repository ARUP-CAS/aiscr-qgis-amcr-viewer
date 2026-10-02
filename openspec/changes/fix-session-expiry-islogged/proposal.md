# Proposal

## Why

Login to digiarchiv expires after 1 h of inactivity (`sessionTimeout: 3600`)
and the server then silently treats the request as anonymous: HTTP 200, no
`error`, only `pristupnost=A` data. The plugin detects expiry only by HTTP 401
or error text, which never arrives, so a logged-in user who downloads again
after a pause gets incomplete data without any warning (issue #72, verified
manually in QGIS and against the live API).

## What Changes

- Before each download the plugin checks the login state with
  `GET /api/user/islogged` whenever the user is (or should be) logged in –
  i.e. an in-memory session exists or credentials are stored.
- When the server answers `{"error": "nologged"}` and credentials are stored,
  the plugin logs in again and continues the download with the new session.
- When the re-login fails (or credentials are missing), the plugin warns in
  the QGIS message bar that the download runs anonymously and returns only
  records with access level A – not only in the log.
- When the check itself cannot be completed (network error, invalid JSON),
  the download is not blocked; the plugin logs a warning and proceeds.
- The existing error-text based detection (`_is_auth_error`) stays as
  a fallback; it is documented as not triggered by the current server.
- Version bump + changelog (`metadata.txt`, `CITATION.cff`).

Out of scope:

- Keeping the session alive in the background (polling `islogged` does not
  extend it anyway).
- Showing the user's access level in the UI (`islogged?wantsUser=true`).
- Codelist updates: `amcr_codelists` calls the API with plain `requests`
  without the session, so login state does not affect them today.

## Capabilities

### New Capabilities

- `amcr-session`: login session against digiarchiv – validating the session
  before a download, transparent re-login and informing the user when data
  are downloaded anonymously.

### Modified Capabilities

<!-- none – openspec/specs/ is empty -->

## Impact

- Code: `amcr_viewer/amcr_tools.py` (new login-state check, call at the start
  of `load_amcr_data`, message bar warning); `tests/smoke_test.py` (offline
  test of the check with a mocked HTTP session).
- API: one extra `GET /api/user/islogged` per download, only when the user is
  logged in or has stored credentials; anonymous users are unaffected.
- No new dependencies; Qt5/Qt6 compatibility rules from `AGENTS.md` apply.
