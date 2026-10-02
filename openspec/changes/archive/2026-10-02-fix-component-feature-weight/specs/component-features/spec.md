# Spec Delta

## Purpose

Describes how components of fieldwork events and sites become map features
and how their weight lets spatial analyses count a shared geometry once.

## ADDED Requirements

### Requirement: Weight of component features sums to one per DJ
When components are loaded as features, each feature SHALL carry the weight
`prvek_vaha = 1/n`, where *n* is the number of features created from the
same documentation unit in this download. Components excluded by the period
or area filter SHALL NOT count towards *n*.

#### Scenario: No component filter
- **WHEN** a documentation unit has 4 components and no period or area filter is set
- **THEN** 4 features are created, each with weight 0.25

#### Scenario: Filter keeps some components
- **WHEN** a documentation unit has 4 components and the period filter matches 1 of them
- **THEN** 1 feature is created with weight 1

#### Scenario: Filter keeps two of three components
- **WHEN** a documentation unit has 3 components and the filter matches 2 of them
- **THEN** 2 features are created, each with weight 0.5, and their weights sum to 1

### Requirement: Documentation unit without components has weight one
When components are loaded and a documentation unit has no component, the
single feature created for it SHALL have weight 1 and empty component
fields.

#### Scenario: DJ without components, no filter
- **WHEN** a documentation unit with a PIAN has no components and no component filter is set
- **THEN** one feature is created with empty component fields and weight 1
