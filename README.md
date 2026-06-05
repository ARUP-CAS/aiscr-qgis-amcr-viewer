# AMCR Viewer: QGIS Plugin Documentation

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)

**Platform:** QGIS 3.4.0–4.99.0

**Module Type:** Data Acquisition & Visualization

**Source Data:** Archaeological Map of the Czech Republic (AIS CR)

---

## 1. Overview

**AMCR Viewer** is a QGIS plugin designed to facilitate direct access to the Digital Archive of the Archaeological Map of the Czech Republic (AMČR). It allows researchers to **query, retrieve, and visualize *Fieldwork events* and *Sites* data (metadata and geometry) directly within the GIS environment**, eliminating the need to manually export data from the web interface. Both *Fieldwork events* and *Sites* layers may optionally include component-level data (period and activity area) embedded directly in the attribute table. The plugin supports both **anonymous (public) access** and **authenticated access** for users with an AMČR account.

### Key Features

* **Spatial Querying:** Option to filter records based on the current map canvas extent (Bounding Box).
* **Advanced Attribute Filtering:** Supports multi-criteria filtering using controlled vocabularies.
* **Dynamic Geometry Retrieval:** Automatically downloads and categorizes spatial data into Point, Line, and Polygon layers.
* **Semantic Interoperability:** Automatically translates internal system codes into human-readable labels using the AIS CR API.
* **Authenticated Access:** Users with an AMČR account can log in to access non-public records.

## 2. Installation Guide

**Install the plugin from QGIS plugin repository.**

**OR**

1. *Obtain the [plugin distribution package](https://github.com/ARUP-CAS/aiscr-qgis-amcr-viewer/releases) (ZIP archive containing the `amcr_viewer` directory).*
2. *Launch QGIS.*
3. *Navigate to Plugins → Manage and Install Plugins...*
4. *Select the Install from ZIP tab.*
5. *Locate the source ZIP file and click Install Plugin.*
6. *Upon successful installation, the AMCR Viewer button will appear in the toolbar.*

## 3. User Manual

### 3.1 Authentication (Optional)

By default, the plugin accesses only publicly available records (accessibility = anonymous). To access non-public data, log in using your AMČR account:

* Click the dropdown arrow on the AMCR Viewer toolbar button and select **Přihlásit se**.
* Enter your e-mail and password. Credentials are encrypted and stored securely in the **QGIS Authentication Manager** (DPAPI on Windows, Keychain on macOS, encrypted SQLite on Linux).
* Stored credentials are reused automatically across sessions. To update or remove them, open the login dialog again.

### 3.2 Data Retrieval

To initiate a search query, click either the **Stáhnout data akcí** or the **Stáhnout data lokalit** option from the dropdown menu. The filter dialog provides the following options. Shown options vary based on the chosen tool.

* **Spatial Filter:** *Checkbox "Omezit vyhledávání rozsahem okna":* If checked, the query is restricted to the geographical area currently visible in the QGIS canvas. If unchecked, the query searches the entire database (use with caution regarding data volume).
* **Positive findings only:** If checked, only *PIANs* belonging to Documentation units marked as "Type of evidence" = "positive" are included. *(Fieldwork events only.)*

* **Attribute Filters:**
  * The dialog uses "Picker" widgets for controlled vocabularies (common: Region, District, Cadastral area, Period, Activity Area, *PIAN* accuracy, Accessibility; *events* related: Organisation, Researcher, Event type; *sites* related: Site type and class, Level of confidence, State of preservation).
  * Click **Vybrat...** to open a searchable selection window. Multiple values can be selected simultaneously (Logic: OR).

* **Codelists (Hesláře):**
  * Controlled vocabularies are downloaded from the AMČR OAI-PMH API and cached locally in `codelists/heslar.csv`.
  * To refresh all codelists, click the **Aktualizovat hesláře 🔄** button in the filter dialog. This runs as a background task and may take a few minutes.

* **Components:** Check **Načíst komponenty** to include period and activity area data directly in the output layers.
  > ⚠ When components are loaded, spatial features are duplicated — each feature corresponds to one component. Spatial analyses (areas, counts) may be inaccurate.

* If no filter is used, all accessible Fieldwork events/PIANs are returned (the number of records is capped at 20 000; it is advisable to set at least one filter).

For a more in-depth tutorial refer to the [AMČR Documentation](https://amcr-help.aiscr.cz/digiarchiv/qgis-viewer.html) (only in Czech).

### 3.3 Layer Structure & Attributes

Upon successful retrieval, the plugin generates up to three temporary memory layers:

1. **AMCR\_[Akce|Lokalita]\_Polygony**
2. **AMCR\_[Akce|Lokalita]\_Linie**
3. **AMCR\_[Akce|Lokalita]\_Body**

Layers are only created if the query returns features of the corresponding geometry type. All layers share the same attribute schema.

#### 3.3.1 Common fields

| Field | Description |
| --- | --- |
| pian | PIAN (spatial identifier) ID |
| presnost | Spatial deviation \[units/tens/hundreds of meters/defined by cadastre\] |
| pian\_typ | \[point/line/polygon\] |
| dj | Documentation unit ID |
| typ\_dj | \[trench/event part/whole event/cadastral territory\] |
| definicni\_body | Feature centroid in WGS-84 coordinate system |
| akce / lokalita | Fieldwork event / Site ID |
| odkaz\_do\_digiarchivu | Link to the record in the Digital Archive |
| okres | District |
| katastr | Main cadastral area |
| dalsi\_katastry | Other cadastral areas, if the event extends beyond the main cadastre |
| Přístupnost | Record accessibility \[A/B/C/D\] |

#### 3.3.2 Fields related to *Fieldwork events*

| Field | Description |
| --- | --- |
| akce\_lokalizace | Verbal description of the event location |
| vedouci | Main fieldwork manager |
| organizace | Organisation conducting the research |
| specifikace\_data | \[exact date/exact years/sometime in years\] |
| zahajeni | Event start date |
| ukonceni | Event end date |
| hlavni\_typ | Primary research method |
| vedlejsi\_typ | Secondary research method |
| zjisteni | Did the research reveal archaeological contexts? \[positive/negative\] |
| nahrazuje\_NZ | Replaces a fieldwork report? \[yes/no\] |

#### 3.3.3 Fields related to *Sites*

| Field | Description |
| --- | --- |
| nazev\_lokality | Site name |
| popis\_lokality | Site description |
| typ\_lokality | Site classification by definition method |
| druh\_lokality | Site classification by the nature of identified field relics |
| zachovalost | Site preservation state |

#### 3.3.4 Component fields (only when *Načíst komponenty* is checked)

| Field | Description |
| --- | --- |
| komponenta | Component ID |
| komponenta\_areal | Activity area \[settlement/burial area/field/…\] |
| komponenta\_obdobi | Period \[Neolithic/High Middle Ages–Modern Period/…\] |

## 4. Technical Architecture

The plugin is developed in **Python 3** using the **PyQt6** framework for the GUI and the **Requests** library for HTTP communication.

### 4.1 File Structure

* `amcr_viewer.py`: Entry point; handles GUI integration, toolbar/menu setup, and login flow.
* `amcr_dialog.py`: Manages the UI logic, including `AmcrFilterDialog`, `FilterableSelectionDialog`, and `LoginDialog`.
* `amcr_tools.py`: Core logic module. Handles authentication, API requests, pagination, data parsing, and vector layer generation.
* `amcr_codelists.py`: Manages local caching of controlled vocabularies (`codelists/heslar.csv`) downloaded via OAI-PMH.

### 4.2 Data Flow & API Integration

The plugin interacts with the following endpoints:

1. **Login API:**
   * Endpoint: `https://digiarchiv.aiscr.cz/api/user/login`
   * Method: `POST`
   * Returns a session cookie used for subsequent authenticated requests.
   * Credentials are stored in the QGIS Authentication Manager; the session is restored automatically if it expires mid-download.

2. **Search API (Solr):**
   * Endpoint: `https://digiarchiv.aiscr.cz/api/search/query`
   * Method: `GET`
   * Parameters: `entity=akce|lokalita|pian`, `rows/page` (pagination), `mapa=true`.
   * Logic: Paginated in batches of 500 records (metadata) and 200 records (geometries). A safety cap of 20 000 records is enforced.

3. **Translation API:**
   * Endpoint: `https://digiarchiv.aiscr.cz/api/assets/i18n/cs.json`
   * Function: Retrieves the mapping between system codes (e.g. `HES-xxxx`) and Czech labels. Cached in memory for the session.

4. **Codelists API (OAI-PMH):**
   * Endpoint: `https://api.aiscr.cz/2.2/oai`
   * Used for downloading controlled vocabularies (periods, regions, organisations, etc.) on demand.

### 4.3 Data Persistence

* **Vocabularies:** Stored in `codelists/heslar.csv`; updated on user request via the background task.
* **Layers:** Output layers are created as `memory` layers. They are non-persistent and will be lost if QGIS is closed without saving.

### 4.4 Constraints

* **Record Limit:** A safety cap of 20 000 records is enforced.
* **Batch Processing:** Geometry fetching is batched (200 IDs per request) to comply with URL length limitations and server load balancing.
* **Component duplication:** When components are loaded, each output feature corresponds to one component rather than one documentation unit. A single PIAN may therefore appear multiple times in the layer.

## 5. Links and resources

* [AMCR/Digiarchive Documentation](https://amcr-help.aiscr.cz/) (only in Czech).
* [AMCR Viewer tutorial](https://amcr-help.aiscr.cz/digiarchiv/qgis-viewer.html) (only in Czech).
* [Import/Export. Pluginy propojující QGIS s AMČR \[poster\]](https://zenodo.org/records/20504909) (only in Czech; valid for v1.3.2).
