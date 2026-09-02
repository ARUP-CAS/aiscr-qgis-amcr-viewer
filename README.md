# AMČR Viewer — QGIS plugin

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![QGIS 3.44 – 4.x](https://img.shields.io/badge/QGIS-3.44%20%E2%80%93%204.x-589632.svg)](https://qgis.org/)
[![Code quality](https://github.com/ARUP-CAS/aiscr-qgis-amcr-viewer/actions/workflows/code_quality.yml/badge.svg)](https://github.com/ARUP-CAS/aiscr-qgis-amcr-viewer/actions/workflows/code_quality.yml)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.18609813.svg)](https://doi.org/10.5281/zenodo.18609813)

**AMČR Viewer** queries the Digital Archive of the Archaeological Map of the
Czech Republic (AMČR) and turns the result into ordinary QGIS vector layers.
It removes the manual export/import round trip: you filter the archive from
inside QGIS and the matching records arrive as point, line and polygon layers
with a full attribute table.

| | |
| --- | --- |
| **Source data** | [Digital Archive AMČR](https://digiarchiv.aiscr.cz/) (AIS CR) |
| **Supported QGIS** | 3.44.0 – 4.99.0 (Qt 5 and Qt 6) |
| **Output** | temporary `memory` layers, S-JTSK / **EPSG:5514** |
| **Access** | anonymous by default; optional login for non-public records |
| **UI language** | Czech |
| **Licence** | GPL-3.0 |

---

## 1. What it can download

The plugin covers three AMČR record types. Each has its own menu entry, its
own set of filters and its own attribute table.

| Entity | Menu entry | What it is |
| --- | --- | --- |
| **Fieldwork events** (`akce`) | *Stáhnout data akcí* | Records of archaeological finds and observations tied to a place, a responsible body and a time of execution. |
| **Sites** (`lokalita`) | *Stáhnout data lokalit* | Records tied to a site, its characteristic archaeological manifestation and presumed function. |
| **Individual finds** (`samostatny_nalez`) | *Stáhnout data samostatných nálezů* | Records of individual movable finds reported through **AMČR-PAS**, the portal for amateur collaborators. |

Fieldwork events and Sites can additionally carry **component** data (period
and activity area) directly in the attribute table. Individual finds have no
components — period and dating are attributes of the find itself.

### Key features

* **Spatial querying** — restrict the query to the current map canvas extent.
* **Multi-criteria attribute filtering** driven by AMČR controlled
  vocabularies (*hesláře*), with a searchable multi-select picker per filter.
* **Date range filtering** for fieldwork start/end and for the date of finding.
* **Automatic geometry retrieval**, split into Point, Line and Polygon layers
  and reprojected to S-JTSK.
* **Human-readable labels** — internal codes (`HES-xxxxxx`) are translated via
  the AIS CR translation dictionary.
* **Authenticated access** — an AMČR account unlocks non-public records;
  credentials are stored encrypted in the QGIS Authentication Manager.

---

## 2. Installation

### From the QGIS plugin repository (recommended)

*Plugins → Manage and Install Plugins… → search for* **AMČR Viewer** *→
Install*.

### From a ZIP archive (older versions, or a build from source)

1. Download a [release package](https://github.com/ARUP-CAS/aiscr-qgis-amcr-viewer/releases)
   (a ZIP containing the `amcr_viewer` directory).
2. In QGIS go to *Plugins → Manage and Install Plugins… → Install from ZIP*.
3. Select the archive and click *Install Plugin*.

Every successful CI run also publishes a ready-to-install `amcr_viewer.zip`
as a build artifact, which is handy for testing a branch before release.

After installation the **AMČR Viewer** button appears in the toolbar as a
dropdown.

### Requirements

The plugin needs the **`requests`** library. It ships with the QGIS installers
for Windows and macOS. On Linux distribution packages it may have to be
installed separately (e.g. `python3-requests`).

---

## 3. User manual

### 3.1 Toolbar and menu

The toolbar button is a dropdown; the default action is *Stáhnout data akcí*.

| Menu entry | Action |
| --- | --- |
| *Stáhnout data akcí* | Opens the filter dialog for Fieldwork events. |
| *Stáhnout data samostatných nálezů* | Opens the filter dialog for Individual finds. |
| *Stáhnout data lokalit* | Opens the filter dialog for Sites. |
| *Přihlásit se* | Opens the login dialog (see 3.2). |
| *Nápověda AMČR Help* | Opens the online documentation in a browser. |

### 3.2 Authentication (optional)

By default the plugin sees only publicly accessible records. Logging in with
an AMČR account extends the result set to everything the account is allowed
to see.

* The credentials are **verified against the API before they are stored** —
  a wrong password never reaches the Authentication Manager. If the server is
  unreachable, the plugin offers to store them unverified.
* They are then saved encrypted in the **QGIS Authentication Manager** (DPAPI
  on Windows, Keychain on macOS, encrypted SQLite on Linux). QGIS will ask for
  its master password.
* Stored credentials are reused across QGIS sessions. If the session cookie
  expires mid-download, the plugin re-authenticates automatically and repeats
  the request.
* Reopening the login dialog lets you change the e-mail (leave the password
  blank to keep the stored one) or remove the credentials entirely
  (*Odebrat uložené přihlašovací údaje*).

### 3.3 The filter dialog

Filters of different categories are combined with **AND**; multiple values
inside one filter are combined with **OR**. A filter left empty means "no
restriction". Click *Vybrat…* to open a searchable, checkable list.

#### Availability per entity

| Filter (Czech UI label) | Events | Sites | Ind. finds | API parameter |
| --- | :---: | :---: | :---: | --- |
| Omezit vyhledávání rozsahem okna | ✓ | ✓ | ✓ | `loc_rpt` |
| Pouze pozitivní zjištění | ✓ | — | — | `posevidence` |
| Pouze projektové akce | ✓ | — | — | `proj_akce` |
| Kraj | ✓ | ✓ | ✓ | `f_kraj` |
| Okres | ✓ | ✓ | ✓ | `f_okres` |
| Katastr | ✓ | ✓ | ✓ | `f_katastr` |
| Přístupnost | ✓ | ✓ | ✓ | `pristupnost` |
| PIAN – přesnost | ✓ | ✓ | — | `f_pian_presnost` |
| Organizace | ✓ | — | ✓ | `f_organizace` |
| Vedoucí výzkumu | ✓ | — | — | `f_vedouci` |
| Typ výzkumu | ✓ | — | — | `f_typ_vyzkumu` |
| Datum — *Zahájení* / *Ukončení* | ✓ | — | — | `akce_datum_zahajeni`, `akce_datum_ukonceni` |
| Lokalita – typ | — | ✓ | — | `f_typ_lokality` |
| Lokalita – druh | — | ✓ | — | `f_druh_lokality` |
| Lokalita – jistota určení | — | ✓ | — | `f_jistota` |
| Lokalita – stav dochování | — | ✓ | — | `f_lokalita_zachovalost` |
| Období | ✓ | ✓ | ✓ | `f_obdobi` |
| Kategorie nálezu | — | — | ✓ | `f_kategorie` |
| Druh nálezu | — | — | ✓ | `f_druh_nalezu` |
| Materiál | — | — | ✓ | `f_specifikace` |
| Okolnosti nálezu | — | — | ✓ | `f_nalezove_okolnosti` |
| Nálezce | — | — | ✓ | `f_nalezce` |
| Datum nálezu | — | — | ✓ | `samostatny_nalez_datum_nalezu` |
| Areál | ✓ | ✓ | — | `f_areal` |
| Načíst komponenty | ✓ | ✓ | — | — |

#### Spatial restriction

*Omezit vyhledávání rozsahem okna* is **checked by default**. The canvas
extent is transformed from the project CRS to WGS-84 and sent as a bounding
box. Unchecking it queries the whole database — do so with an attribute
filter in place, otherwise you will hit the record cap (see 4.5).

#### PIAN accuracy has a non-empty default

> ⚠ *PIAN – přesnost* is the one filter that is **pre-selected**. For
> Fieldwork events and Sites the dialog starts with *odchylka jednotky metrů*,
> *odchylka desítky metrů* and *odchylka stovky metrů* checked, so an
> otherwise untouched dialog already sends `f_pian_presnost`. Records
> localised only to a cadastral territory are excluded until you open the
> picker and add that level yourself.

#### Date ranges

Each date block has a *from* and a *to* picker; an empty picker shows
*neomezeno* and means an open bound. The API rejects a one-sided range, so the
plugin substitutes a sentinel (`0001-01-01` / `9999-12-31`) for the empty
side. A block with **both** pickers empty adds no filter at all.

A reversed range (start later than end) is refused when you confirm the
dialog — such a query would come back empty and would be indistinguishable
from a genuinely empty result.

#### Codelists (hesláře)

The controlled vocabularies behind the pickers are cached in
`amcr_viewer/codelists/heslar.csv` and ship with the plugin. Click
**Aktualizovat hesláře 🔄** to rebuild the file from the live APIs; it runs as
a background QGIS task with a progress bar and takes a few minutes.

Most codelists come from the AMČR **OAI-PMH** endpoint. Two are built from
Digiarchiv **search facets** instead, because they are lists of people rather
than a published vocabulary: *Vedoucí výzkumu* (`f_vedouci`, faceted over
fieldwork events) and *Nálezce* (`f_nalezce`, faceted over individual finds).

#### Components

Check **Načíst komponenty** (Events and Sites only) to bring the period and
activity area of each component into the output layer.

> ⚠ With components loaded, spatial features are **duplicated** — one feature
> per component. Areas and feature counts computed on such a layer are
> misleading.

Note that *Období* and *Areál* also act as component filters even when the
box is unchecked: a documentation unit whose components match nothing is
dropped from the result.

### 3.4 Output layers

Up to three temporary `memory` layers are created per download, in **S-JTSK
(EPSG:5514)**:

* `AMCR_Akce_Body` / `_Linie` / `_Polygony`
* `AMCR_Lokalita_Body` / `_Linie` / `_Polygony`
* `AMCR_Samostatný_nález_Body` / `_Linie` / `_Polygony`

A layer is only created if the query actually returned that geometry type.
All layers of one download share the same attribute schema. Field names are
ASCII; the human-readable names visible in the attribute table are QGIS field
aliases.

> Memory layers are **not persistent** — export them (GeoPackage, Shapefile,
> …) before closing the project.

Geometry is taken from the record's S-JTSK WKT when present; otherwise the
WGS-84 fallback is reprojected. Invalid geometries are repaired rather than
dropped.

The tables below group the fields by meaning. In the layer they appear in the
order *common → entity-specific → `pristupnost` → component fields*.

#### Common fields

| Field | Alias | Description |
| --- | --- | --- |
| `pian` | PIAN | Spatial unit (PIAN) identifier. *Events and Sites only.* |
| `presnost` | Přesnost | Spatial accuracy \[units / tens / hundreds of metres / defined by cadastre\]. *Events and Sites only.* |
| `pian_typ` | PIAN – typ | \[point / line / polygon\]. *Events and Sites only.* |
| `dj` | Dokumentační jednotka | Documentation unit identifier. *Events and Sites only.* |
| `typ_dj` | Typ dokumentační jednotky | \[trench / event part / whole event / cadastral territory\]. *Events and Sites only.* |
| `akce` / `lokalita` / `samostatny_nalez` | Akce / Lokalita / Samostatný nález | Record identifier. |
| `definicni_body` | Definiční bod(y) (WGS-84) | Feature centroid(s) in WGS-84. |
| `odkaz_do_digiarchivu` | Odkaz do Digitálního archivu AMČR | Permalink to the record. |
| `okres` | Okres | District. |
| `katastr` | Katastr | Main cadastral area. |
| `dalsi_katastry` | Další katastry | Other cadastral areas. *Always empty for individual finds.* |
| `pristupnost` | Přístupnost | Record accessibility \[A/B/C/D\]. |

#### Fieldwork event fields

| Field | Alias | Description |
| --- | --- | --- |
| `akce_lokalizace` | Akce – lokalizace | Verbal description of the location. |
| `vedouci` | Vedoucí akce | Main fieldwork manager. |
| `organizace` | Organizace | Organisation conducting the research. |
| `specifikace_data` | Specifikace data | \[exact date / exact years / sometime in years\]. |
| `zahajeni` | Datum zahájeni | Start date. |
| `ukonceni` | Datum ukončení | End date. |
| `hlavni_typ` | Hlavní typ | Primary research method. |
| `vedlejsi_typ` | Vedlejší typ | Secondary research methods. |
| `zjisteni` | Zjištění | Whether the **documentation unit** is positive or negative evidence \[Pozitivní / Negativní\]. |
| `nahrazuje_NZ` | Akce – nahrazuje NZ | Replaces a fieldwork report \[Ano / Ne\]. |
| `projekt` | Projekt | Identifier of the related project, if any. |

#### Site fields

| Field | Alias | Description |
| --- | --- | --- |
| `nazev_lokality` | Název lokality | Site name. |
| `popis_lokality` | Popis lokality | Site description. |
| `typ_lokality` | Typ lokality | Site classification by definition method. |
| `druh_lokality` | Druh lokality | Site classification by the nature of the field relics. |
| `zachovalost` | Zachovalost | State of preservation. |

#### Individual find fields

| Field | Alias | Description |
| --- | --- | --- |
| `projekt` | Projekt | Identifier of the related project. |
| `nalezce` | Nálezce | Finder. |
| `datum` | Datum nálezu | Date of finding. |
| `okolnosti` | Nálezové okolnosti | Finding context. |
| `hloubka_cm` | Hloubka (cm) | Depth below surface. |
| `lokalizace` | Lokalizace | Verbal description of the find spot. |
| `obdobi` | Období | Period. |
| `presna_datace` | Přesná datace | Precise dating, if known. |
| `nalez` | Nález | Find class. |
| `material` | Materiál | Find specification / material. |
| `pocet` | Počet předmětů | Number of objects. |
| `poznamka` | Poznámka/bližší popis | Note or closer description. |
| `pred_org` | Předáno organizaci | Organisation the find was handed over to. |
| `evidencni` | Evidenční číslo | Reference number. |

#### Component fields (only with *Načíst komponenty*)

| Field | Alias | Description |
| --- | --- | --- |
| `komponenta` | Komponenta | Component identifier. |
| `komponenta_areal` | Areál | Activity area \[settlement / burial area / field / …\]. |
| `komponenta_obdobi` | Období | Period \[Neolithic / High Middle Ages–Modern Period / …\]. |

### 3.5 When a query returns nothing

Progress and errors are written to the QGIS *Messages* panel, tab **AMČR**
(login goes to **AMČR login**). The log contains the **exact request URL**,
so a suspicious query can be replayed in a browser instead of being
reconstructed from the code. Distinct messages tell apart an empty result, an
API error, a network failure and a result without any geometry.

Only one download can run at a time; starting a second one while the first is
still running is refused with a message.

For a step-by-step tutorial see the
[AMČR documentation](https://amcr-help.aiscr.cz/digiarchiv/qgis-viewer.html)
(Czech only).

---

## 4. Technical notes

The plugin is plain **Python 3** with **`requests`** for HTTP. The GUI is
built through the **`qgis.PyQt`** compatibility layer rather than importing
`PyQt5`/`PyQt6` directly, which is what lets a single source tree run on both
QGIS 3.44 (Qt 5) and QGIS 4 (Qt 6). Every enum is referenced in its scoped
form (`Qt.CheckState.Checked`, …), as required by Qt 6.

### 4.1 Repository layout

```
amcr_viewer/            the plugin package (this is what gets zipped)
  __init__.py           classFactory() entry point for QGIS
  amcr_viewer.py        toolbar/menu integration, login flow, dispatch
  amcr_dialog.py        AmcrFilterDialog, FilterableSelectionDialog,
                        LoginDialog, UpdateCodelistsTask
  amcr_tools.py         API access, pagination, parsing, layer building
  amcr_codelists.py     codelist download and CSV cache
  codelists/heslar.csv  cached controlled vocabularies
  i18n/                 Qt translation files
  *.png                 toolbar and menu icons
  resources.py          generated by pyrcc, currently unused
  metadata.txt          plugin metadata and changelog
  .flake8               lint config, read by the plugins.qgis.org scanner
tests/
  check_sources.py      source hygiene checks (no QGIS needed)
  smoke_test.py         loads the plugin in a real, headless QGIS
.github/workflows/      CI (code quality, release packaging)
pyproject.toml          ruff configuration
AGENTS.md               contributor and AI-agent guidelines
```

### 4.2 API endpoints

| Purpose | Endpoint | Notes |
| --- | --- | --- |
| Login | `POST https://digiarchiv.aiscr.cz/api/user/login` | Returns a session cookie. Errors arrive with HTTP 200 and an `error` key. |
| Search | `GET https://digiarchiv.aiscr.cz/api/search/query` | `entity=akce\|lokalita\|samostatny_nalez\|pian`, `mapa=true`, paginated. |
| Translations | `GET https://digiarchiv.aiscr.cz/api/assets/i18n/cs.json` | Code → Czech label; cached in memory for the session. |
| Codelists | `GET https://api.aiscr.cz/2.2/oai` | OAI-PMH `ListRecords`, with resumption tokens. |

### 4.3 Processing pipeline

1. **Metadata** are paged in batches of **500** records, deduplicated by
   `ident_cely`, until the reported `numFound` is reached or the cap is hit.
2. Records **without geometry are skipped**; the rest are expanded into
   documentation units and — if requested — into components.
3. **Geometries** (PIAN) are fetched separately in batches of **200**
   identifiers, to stay under URL length limits.
4. Features are built, reprojected to EPSG:5514, sorted by geometry type and
   added to the project in a single batch per layer.

### 4.4 Data persistence

* **Codelists** — `amcr_viewer/codelists/heslar.csv`, rewritten only when the
  user asks for an update.
* **Credentials** — QGIS Authentication Manager; the config ID is kept in
  `QSettings` under `amcr_viewer/auth_config_id`.
* **Layers** — `memory` only, lost when QGIS closes.

### 4.5 Limits

* **20 000 records** per query (safety cap; QGIS would otherwise freeze).
* **500** records per metadata request, **200** identifiers per geometry
  request.
* With components loaded, one output feature equals one component, so a
  single PIAN can appear several times in the layer.

---

## 5. Development

Contributor rules, branch naming and the manual QGIS test checklist live in
[`AGENTS.md`](./AGENTS.md).

Every pull request runs
[`.github/workflows/code_quality.yml`](.github/workflows/code_quality.yml),
which mirrors what plugins.qgis.org checks on upload and adds what it does
not:

| Job | What it does |
| --- | --- |
| **Lint a bezpečnost** | `tests/check_sources.py`, bandit, detect-secrets, flake8, ruff |
| **Kompatibilita s Qt6** | `pyqgis4-checker` in dry-run mode |
| **Smoke test** | loads the plugin in headless QGIS — both `ltr` (Qt 5) and `stable` (Qt 6) |
| **Balíček pluginu** | builds `amcr_viewer.zip`, asserts its contents, uploads it as an artifact |

Reproducing them locally:

```bash
python3 tests/check_sources.py
ruff check .
flake8 --config amcr_viewer/.flake8 amcr_viewer/
bandit -r amcr_viewer/
docker run --rm -v "$PWD:/work:ro" -w /work --user "$(id -u):$(id -g)" \
  -e HOME=/tmp qgis/qgis:stable python3 tests/smoke_test.py
```

---

## 6. Links and resources

* [AMČR / Digiarchiv documentation](https://amcr-help.aiscr.cz/) (Czech only)
* [AMČR Viewer tutorial](https://amcr-help.aiscr.cz/digiarchiv/qgis-viewer.html)
  (Czech only)
* [AMČR-PAS](https://amcr-info.aiscr.cz/amcr-pas/) — the amateur collaborator
  portal behind the Individual finds records
* [Import/Export. Pluginy propojující QGIS s AMČR \[poster\]](https://zenodo.org/records/20504909)
  (Czech only; describes v1.3.2)

## Citing

Cite the plugin using [`CITATION.cff`](./CITATION.cff) or the concept DOI
[10.5281/zenodo.18609813](https://doi.org/10.5281/zenodo.18609813), which
always resolves to the latest release.

## Licence

GPL-3.0 — see [`LICENSE`](./LICENSE).
