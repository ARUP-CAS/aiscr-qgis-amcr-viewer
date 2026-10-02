# Spec Delta

## Purpose

Keeps a logged-in user's data downloads from digiarchiv running under a valid
login, and makes it visible when a download falls back to anonymous access.

## ADDED Requirements

### Requirement: Login state is verified before a download
Before starting a data download, the plugin SHALL ask the server whether the
current session is logged in, whenever an in-memory session exists or login
credentials are stored. Users with neither SHALL download anonymously without
this check.

#### Scenario: Valid session
- **WHEN** a session exists and the server reports it as logged in
- **THEN** the download proceeds with that session and no re-login happens

#### Scenario: Anonymous user without stored credentials
- **WHEN** no session exists and no credentials are stored
- **THEN** no login-state request is sent and the download proceeds anonymously without a warning

### Requirement: Expired login is renewed transparently
When the server reports the session as not logged in and credentials are
stored, the plugin SHALL log in again and run the whole download with the new
session.

#### Scenario: Session expired after inactivity
- **WHEN** the user downloads data more than one hour after the previous download within the same QGIS run
- **THEN** the plugin logs in again with the stored credentials and the download returns the same records as for a fresh login

#### Scenario: No session yet, credentials stored
- **WHEN** the first download after QGIS start is requested and credentials are stored
- **THEN** the plugin logs in and verifies that the new session is logged in before downloading

### Requirement: Anonymous fallback is reported to the user
When the plugin expected to be logged in but cannot obtain a logged-in
session, it SHALL show a warning in the QGIS message bar stating that the
download runs anonymously and contains only records with access level A.

#### Scenario: Re-login fails
- **WHEN** the session has expired and logging in again with stored credentials fails
- **THEN** a warning appears in the message bar and the download continues anonymously

#### Scenario: Session expired and credentials removed
- **WHEN** an in-memory session has expired and no credentials are stored any more
- **THEN** a warning appears in the message bar and the download continues anonymously

### Requirement: Failed state check does not block the download
If the login-state check cannot be completed (network error or a response
that is not valid JSON), the plugin SHALL log a warning and proceed with the
download using the current session.

#### Scenario: Login-state endpoint unreachable
- **WHEN** the login-state request fails with a network error
- **THEN** a warning is written to the log and the download is attempted as usual

### Requirement: Removing stored credentials logs the user out
When the user removes the stored credentials, the plugin SHALL log the
current session out on the server and discard it, so that later downloads
run anonymously without restarting QGIS.

#### Scenario: Credentials removed while logged in
- **WHEN** the user removes the stored credentials while a logged-in session exists
- **THEN** the session is logged out on the server and the next download is anonymous without a warning

#### Scenario: Server unreachable during logout
- **WHEN** the logout request fails with a network error
- **THEN** the session is still discarded locally and the user is told the next download will be anonymous
