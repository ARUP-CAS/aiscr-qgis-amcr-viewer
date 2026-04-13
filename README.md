# AMCR Viewer: QGIS Plugin Documentation

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)

**Platform:** QGIS 3.4.0–4.99.0

**Module Type:** Data Acquisition & Visualization

**Source Data:** Archaeological Map of the Czech Republic (AIS CR)

---

## 1. Overview

**AMCR Viewer** is a QGIS plugin designed to facilitate direct access to the Digital Archive of the Archaeological Map of the Czech Republic (AMČR). It allows researchers to **query, retrieve, and visualize *Fieldwork events* and *Sites* data (metadata and geometry) directly within the GIS environment**, eliminating the need to manually export data from the web interface. Both *Fieldwork events* and *Sites* layers may be accompanied by a *Components* layer with additional information. **Only publicly accessible data are supported at the time** (accessibility = anonymous).


### Key Features

* **Spatial Querying:** Option to filter records based on the current map canvas extent (Bounding Box).
* **Advanced Attribute Filtering:** Supports multi-criteria filtering using controlled vocabularies.
* **Dynamic Geometry Retrieval:** Automatically downloads and categorizes spatial data into Point, Line, and Polygon layers.
* **Semantic Interoperability:** Automatically translates internal system codes into human-readable labels using the AIS CR API.

## 2. Installation Guide

**Install the plugin from QGIS plugin repository.**  

**OR**  

*1. Obtain the [plugin distribution package](https://github.com/ARUP-CAS/aiscr-qgis-amcr-viewer/releases) (ZIP archive containing the `amcr_viewer` directory).*  
*2. Launch QGIS.*  
*3. Navigate to Plugins → Manage and Install Plugins...*  
*4. Select the Install from ZIP tab.*  
*5. Locate the source ZIP file and click Install Plugin.*  
*6. Upon successful installation, the AMCR download button (load AMCR data) will appear in the interface.*  

## 3. User Manual

### 3.1 Data Retrieval

To initiate a search query, click either the **Stáhnout data akcí** or the **Stáhnout data lokalit** icon from the dropdown menu. The filter dialog provides the following options. Shown options vary based on the choosed tool.

* **Spatial Filter:** *Checkbox "Limit search to current map extent":* If checked, the query is restricted to the geographical area currently visible in the QGIS canvas. If unchecked, the query searches the entire database (use with caution regarding data volume).
* It is possible to view only those Fieldwork events with positive outcome, if "Positive findings only" is checked. Only *PIANs* marked as (or rather *PIANs* belonging to Documentation units marked as) "Type of evidence" = "positive" are rendered.


* **Attribute Filters:**
  * The dialog utilizes "Picker" widgets for controlled vocabularies (common: Region, District, Cadastral area, Period, Activity Area, *PIAN* accuracy; *events* related: Organisation, Researcher, Event type; *sites* related: Site type and class, Level of confidence, State of preservation).
  * Click **Select...** to open a searchable selection window. Multiple values can be selected simultaneously (Logic: OR).


* **Fieldwork Manager (Dynamic List):**
  * Due to the dynamic nature of the persons database, the list of Fieldwork Managers is retrieved from the AIS CR servers and needs to be updated the first time (and subsequently, if there is need).
  * To refresh the list from the server, click the **Refresh (🔄)** button next to the selection field. This downloads the latest list of researchers from the API.

* **Components:** The *components* data are downloaded as well upon checking the corresponding check box. This enriches the main (*Events* and *Sites*) layers with additional information (period and activity area).

* If no filter is used, all accessible Fieldwork events/PIANs are returned (although the number of Fieldwork events to be loaded is capped at 20000 records; it is advisable to set at least one filter).  

For a more in-depth tutorial refer to the [AMČR Documentation](https://amcr-help.aiscr.cz/digiarchiv/qgis-viewer.html) (only in Czech).

### 3.2 Layer Structure & Attributes

Upon successful retrieval, the plugin generates four temporary memory layers:

1. **AMCR Plochy (Polygons)**
2. **AMČR Linie (Lines)**
3. **AMČR Body (Points)**
4. **AMČR Komponenty (*Components*/no geometry)**

The Attribute Table includes standardized fields with important metadata. The components layer has no geometry on its own and depend solely on a relation with the other three layers.

#### 3.2.1 Fields of the layers with geometry

| Field | Description |
| --- | --- |
| PIAN | PIAN (spatial identifier) ID |
| Přesnost | spatial deviation [in units/tens/hundreds of meters/defined by cadastre] |
| PIAN – typ | [point/line/polygon] |
| Dokumentační jednotka | Documentation unit ID |
| Typ dokumentační jednotky | [trench/event part/whole event/cadastral territory] |
| Definiční bod(y) (WGS-84) | feature centroid in WGS-84 coordinate system |
| Akce/Lokalita | Event/Site ID |
| Odkaz do Digitálního archivu AMČR | link to the Event/Site record in the Digital Archive |
| Okres | district |
| Katastr | main cadastre |
| Další katastr | other cadastres, if the event extends beyond the main cadastre |
| Přístupnost | record accessibility [A/B/C/D] |  

> Common fields

| Field | Description |
| --- | --- |
| Vedoucí akce | main fieldwork manager |
| Organizace | organization conducting the research |
| Specifikace data | [exact date/exact years/sometime in years] |
| Datum zahájení | Event start date |
| Datum ukončení | Event end date |
| Hlavní typ | primary research method [total excavation/pit trench/surface collection survey/…] |
| Vedlejší typ | secondary research method [same options as in Hlavní typ] |
| Zjištění | did the research reveal archaeological contexts? [positive/negative] |
| Akce – lokalizace | verbal description of the event location |
| Akce – nahrazuje NZ | replaces a fieldwork report? [yes/no] |  

> Fields related to *Fieldwork events*  

| Field | Description |
| --- | --- |
| nazev_lokality | site name |
| popis_lokality | site description |
| typ_lokality | site classification by definition method [survey polygon/heritage site/landscape] |
| druh_lokality | site classification by the nature of identified field relics [aerial survey polygon/landscape/remains of settlement/…] |
| zachovalost | site preservation state [buried site/ruin/aboveground remains/…] |

> Fields related to *Sites*

#### 3.2.2 Fields of the *Components* layer

| Field | Description |
| --- | --- |
| komponenta | Component ID |
| dj_id | parent Documentation unit ID |
| komponenta_areal | Activity area [settlement/burial area/field/…] |
| komponenta_obdobi | Period [Neolithic/High Middle Ages–Modern Period/Middle La Tène (LtB–C1)/…] |
| vrstva | system value linking to a specific geometry table with the corresponding documentation unit |

## 4. Technical Architecture

The plugin is developed in **Python 3** using the **PyQt6** framework for the GUI and the **Requests** library for HTTP communication.

### 4.1 File Structure

* `amcr_viewer.py`: Entry point; handles GUI integration and initialization.
* `amcr_dialog.py`: Manages the UI logic, including the custom `FilterableSelectionDialog` for handling large vocabularies.
* `amcr_tools.py`: Core logic module. Handles API requests, pagination, data parsing, and vector layer generation.
* `amcr_codelists.py`: Manages local caching of controlled vocabularies (`codelists/*.csv`).

### 4.2 Data Flow & API Integration

The plugin interacts with three primary endpoints of the AIS CR infrastructure:

1. **Search API (Solr):**
* Endpoint: `https://digiarchiv.aiscr.cz/api/search/query`
* Method: `GET`
* Parameters: `entity=akce`, `rows/page` (pagination).
* Logic: The plugin implements a `while True` loop to handle pagination, processing data in batches of 500 records to ensure stability.

2. **Translation API:**
* Endpoint: `https://digiarchiv.aiscr.cz/api/assets/i18n/cs.json`
* Function: Retrieves the mapping between system codes (e.g., `HES-xxxx`) and Czech labels. This dictionary is cached in memory during the session.

### 4.3 Data Persistence

* **Vocabularies:** Static vocabularies (e.g., Periods, Regions) are stored in `codelists/heslar.csv`.
* **Dynamic Data:** The list of researchers is downloaded on-demand and cached in `codelists/vedouci.csv`.
* **Layers:** Output layers are created as `memory` layers. They are non-persistent and will be lost if QGIS is closed without saving.

### 4.4 Constraints

* **Record Limit:** A safety cap of 20,000 records is enforced.
* **Batch Processing:** Geometry fetching is batched (50 IDs per request) to comply with URL length limitations and server load balancing.

### 4.5 Relational Data Linking
The plugin automatically utilizes advanced QGIS features for data relationship management, specifically Polymorphic Relations. The *Components* layer is dynamically linked within the project to the spatial layers of events and sites via the documentation unit identifier (dj_id). This allows users to immediately see all *components* belonging to a given geometry (point, line, or polygon) directly in the attribute form or the identify features tool, without the need to manually filter or join the data.

## 5. Links and resources

* [AMCR/Digiarchive Documentation](https://amcr-help.aiscr.cz/) (only in Czech).
* [AMCR Viewer tutorial](https://amcr-help.aiscr.cz/digiarchiv/qgis-viewer.html) (only in Czech).
