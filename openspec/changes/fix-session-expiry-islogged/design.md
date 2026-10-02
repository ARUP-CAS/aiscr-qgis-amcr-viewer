# Design

## Context

- The session lives only in memory (`amcr_tools.AMCR_SESSION`, a
  `requests.Session` with the `JSESSIONID` cookie). `_get_session()` logs in
  from stored credentials only when no session object exists, so after QGIS
  start the first download always logs in; an expired session object is
  reused forever.
- All data requests of a download go through `_api_get_json()` (main query
  pages and PIAN batches). `_is_auth_error()` there reacts to HTTP 401 or
  error text – neither occurs on expiry (see proposal.md – Why).
- Server behaviour (verified 2026-10-02, live API):
  `GET /api/user/islogged` → `{"remaining": <s>}` when logged in,
  `{"error": "nologged"}` otherwise, both HTTP 200. It does not extend the
  session; any `search/query` does.
- Codelists (`amcr_codelists.py`) use plain `requests.get` without the
  session – unaffected by login state.

## Goals / Non-Goals

**Goals:**
- One check at the start of `load_amcr_data`, before the first data request.
- Reuse existing login code (`login_to_api`, `LoginDialog.get_credentials`).
- Testable offline: the check takes its HTTP behaviour from the session
  object so the smoke test can inject a fake.

**Non-Goals:**
- Checking before every page / PIAN batch (a download takes seconds to
  minutes and every data request renews the sliding timeout).
- Refactoring session handling into a class.

## Decisions

1. **New helper `_ensure_logged_in() -> str`** in `amcr_tools.py`, returning
   one of `"anonymous"` (no session, no credentials – nothing to check),
   `"logged_in"`, `"relogged"`, `"fallback"` (expected login, ended
   anonymous), `"unknown"` (check failed, proceeding).
   Flow: get session via `_get_session()` (logs in if needed); if none and no
   credentials → `anonymous`; if none but credentials → login failed →
   `fallback`; otherwise call `islogged`; `remaining` → `logged_in`;
   `nologged` → drop session, re-login once, verify again → `relogged` or
   `fallback`; exception / non-JSON → `unknown`.
   *Alternative:* re-login unconditionally before each download – simpler,
   but one POST with the password per download and no way to distinguish a
   real failure; rejected.
   *Alternative:* compare `remaining` with a local timestamp of last request
   – fragile (server timeout may change); rejected.
2. **Caller decides UI.** `load_amcr_data` pushes the message bar warning on
   `fallback`; the helper only logs (keeps it free of `iface` for the test).
3. **Interpretation of the response:** logged in iff the body is a dict with
   key `remaining`. Anything else with an `error` key → not logged in. Unknown
   shape → `unknown` (do not trigger a re-login loop on a format change).
4. **Keep `_is_auth_error`** as a fallback, with a comment that the current
   server never triggers it; removing it brings no benefit and it still
   covers a possible future 401.
5. **Never log the response of `islogged?wantsUser=true`** – we do not use
   that parameter at all; only `remaining` (number) is logged.

6. **Logout on credential removal** – new `logout_from_api()` in
   `amcr_tools.py` called from `LoginDialog._forget_credentials`. The local
   session is dropped first and unconditionally; the server call is best
   effort (a failure is logged and reported in the dialog text). Without
   it, the in-memory session would keep downloading logged-in data until
   QGIS restarts even though the user believes he is "forgotten".

## Risks / Trade-offs

- [Extra request per download] → only for logged-in / credential users; cost
  ~100 ms.
- [Session expires during a very long download] → practically impossible:
  each page request renews the 1 h sliding timeout.
- [Re-login prompts for the QGIS master password] → `get_credentials()` is
  already called on first download after start; behaviour unchanged.
- [`islogged` endpoint changes shape] → `unknown`, logged warning, download
  proceeds as today (no regression).

## Migration Plan

Plain plugin update; no settings or data migration. Rollback = previous
release.
