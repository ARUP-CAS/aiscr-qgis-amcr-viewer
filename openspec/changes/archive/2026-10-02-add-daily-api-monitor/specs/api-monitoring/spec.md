# Spec Delta

## Purpose

Detects changes of the digiarchiv / AMČR OAI API that break or alter what
the AMČR Viewer plugin relies on, within a day of their deployment, and
reports them where maintainers see them.

## ADDED Requirements

### Requirement: The API contract is checked daily
The repository SHALL run, once a day and on manual dispatch, a check of
every API endpoint, parameter and response field the plugin uses, without
credentials, against the production API.

#### Scenario: Scheduled run
- **WHEN** the daily schedule fires on the default branch
- **THEN** both the contract test and the live plugin test run against the production API and their results are published in the run summary

#### Scenario: Manual run on another branch
- **WHEN** a maintainer dispatches the workflow on a non-default branch
- **THEN** the tests run against that branch's plugin code and no issue is opened, updated or closed

### Requirement: Checks follow the plugin, not the API documentation
The contract test SHALL send requests built the way the plugin builds them
and check the response keys, value types and shapes the plugin reads. The
live plugin test SHALL call the plugin's own codelist and download
functions.

#### Scenario: Facet shape changes
- **WHEN** the API returns facet items in a shape different from the one recorded in the contract test
- **THEN** the contract test reports a drift naming the facet field and the old and new shape

#### Scenario: Plugin function returns nothing
- **WHEN** a plugin codelist set or data download returns zero items for an input that returned items before
- **THEN** the live plugin test fails and names the set or data type

### Requirement: Outages are not reported as API changes
A request that times out, fails to connect or returns HTTP 5xx SHALL be
retried; if it still fails, the check SHALL be reported as unavailable,
separately from failures and drifts.

#### Scenario: Server maintenance
- **WHEN** digiarchiv is unreachable during the whole run
- **THEN** the run reports the affected checks as unavailable and no issue is opened

### Requirement: Breaks are reported through one tracking issue
A run with a failure or drift on the default branch SHALL open an issue
labelled `api-monitor`, or update the open one, with the deployed
digiarchiv version and the list of failing checks. A clean run SHALL close
the open issue.

#### Scenario: First failing run
- **WHEN** a scheduled run fails and no open `api-monitor` issue exists
- **THEN** a new issue is opened with the deployed version, failing checks and a link to the run

#### Scenario: Repeated identical failure
- **WHEN** a scheduled run fails with the same set of FAIL/DRIFT checks as the open issue already lists, regardless of which checks are unavailable
- **THEN** no new issue and no new comment is created

#### Scenario: Recovery
- **WHEN** a scheduled run passes while an `api-monitor` issue is open
- **THEN** the issue is closed with a comment linking the passing run
