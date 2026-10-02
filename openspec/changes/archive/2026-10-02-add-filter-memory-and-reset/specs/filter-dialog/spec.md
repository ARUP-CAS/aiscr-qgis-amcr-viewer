# Spec Delta

## Purpose

Keeps the filter dialog's selections between openings within one QGIS run,
so a query can be refined without re-entering it, and gives quick ways back
to the default state.

## ADDED Requirements

### Requirement: Confirmed filters are remembered per data type
When the user confirms the filter dialog with OK, the plugin SHALL remember
the whole form state (all pickers, checkboxes and date ranges) for that
data type, and SHALL restore it the next time the dialog for the same data
type is opened within the same QGIS run. Each data type (Fieldwork events,
Sites, Individual finds) SHALL have its own remembered state.

#### Scenario: Reopening after a download
- **GIVEN** the user opened the Fieldwork events dialog, selected a region and a period, set a start-date range and confirmed with OK
- **WHEN** the user opens the Fieldwork events dialog again
- **THEN** the same region, period and date range are selected and confirming without changes sends the same filters as before

#### Scenario: Data types do not share state
- **GIVEN** filters were confirmed in the Fieldwork events dialog
- **WHEN** the user opens the Sites dialog for the first time
- **THEN** the Sites dialog shows its defaults

#### Scenario: Cancel keeps the previous state
- **GIVEN** a remembered state exists for a data type
- **WHEN** the user changes filters and closes the dialog with Cancel
- **THEN** reopening the dialog shows the remembered state, not the cancelled changes

#### Scenario: Rejected date range is not remembered
- **WHEN** the user confirms a reversed date range and the dialog refuses it
- **THEN** the remembered state is unchanged

### Requirement: Remembered state lives only for the QGIS run
The remembered filters SHALL NOT be written to disk, QGIS settings or the
project; after QGIS is restarted or the plugin is reloaded, every dialog
SHALL open with its defaults.

#### Scenario: QGIS restart
- **GIVEN** filters were confirmed in a previous QGIS run
- **WHEN** the user opens the dialog after restarting QGIS
- **THEN** the dialog shows its defaults

### Requirement: Reset restores the defaults
The filter dialog SHALL offer a reset action that returns every field of
the form to its default: the map-extent restriction checked, *PIAN –
přesnost* with its three pre-selected accuracy levels (where the data type
has it), and every other filter empty. The reset SHALL change only the
form; the remembered state SHALL change only when the dialog is then
confirmed with OK.

#### Scenario: Reset and confirm
- **GIVEN** several filters are set
- **WHEN** the user resets the form and confirms with OK
- **THEN** the sent filters equal those of a dialog opened for the first time, and reopening shows the defaults

#### Scenario: Reset and cancel
- **GIVEN** a remembered state exists
- **WHEN** the user resets the form and closes the dialog with Cancel
- **THEN** reopening the dialog shows the remembered state

### Requirement: A single filter can be returned to its default
Each codelist filter SHALL offer a per-picker action that returns only
that filter to its default value (empty, or the three pre-selected
accuracy levels for *PIAN – přesnost*). The action SHALL be available
only while the filter differs from its default. Returning *PIAN –
přesnost* to its default SHALL restore the three pre-selected accuracy
levels; a completely empty *PIAN – přesnost* (no restriction) SHALL
remain reachable by unchecking all levels in the picker's selection
dialog.

#### Scenario: Clearing one picker
- **GIVEN** a region and a period are selected
- **WHEN** the user clears the region filter
- **THEN** the region filter shows nothing selected, the period stays selected and the region parameter is not sent

#### Scenario: Returning PIAN to its default
- **GIVEN** a Fieldwork events dialog is open with *PIAN – přesnost* at its default three accuracy levels
- **WHEN** the user changes the PIAN selection (for example clears it)
- **THEN** the picker's clear action becomes available and, when used, restores exactly the three pre-selected accuracy levels
- **WHEN** the user unchecks all levels in the *PIAN – přesnost* selection dialog instead
- **THEN** no accuracy restriction is sent

### Requirement: Restored filters are announced
When the dialog opens with a restored state that differs from the
defaults, it SHALL show a notice at the top of the form stating that
filters from the previous search were restored and how many filters
differ from the defaults. The notice SHALL disappear once the form is
reset to the defaults.

#### Scenario: Notice after reopening
- **GIVEN** a region and a period were confirmed
- **WHEN** the dialog is reopened
- **THEN** a notice at the top says filters were restored and that 2 filters are active

#### Scenario: No notice for defaults
- **WHEN** the dialog opens with no remembered state, or with a remembered state equal to the defaults
- **THEN** no notice is shown

### Requirement: Restored values follow the current codelists
When restoring, the plugin SHALL drop selected codes that are no longer
present in the current codelists and SHALL display the remaining
selections with their current codelist labels.

#### Scenario: Code removed by a codelist update
- **GIVEN** a confirmed selection contains a code that a later codelist update removed
- **WHEN** the dialog is reopened
- **THEN** that code is not selected and not sent, and the other selected values remain
