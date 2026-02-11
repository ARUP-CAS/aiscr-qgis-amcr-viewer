# AMCR Viewer: QGIS Plugin Documentation

**Version:** 0.1.1

**Platform:** QGIS 3.4.x

**Module Type:** Data Acquisition & Visualization

**Source Data:** Archaeological Map of the Czech Republic (AIS CR)

---

## 1. Overview

**AMCR Viewer** is a QGIS plugin designed to facilitate direct access to the Digital Archive of the Archaeological Map of the Czech Republic (AMČR). It allows researchers to **query, retrieve, and visualize Fieldwork events[^1] data (metadata and geometry) directly within the GIS environment**, eliminating the need to manually export data from the web interface. **Only publicly accessible data are supported at the time** (accessibility = anonymous).

[^1]: Only Fieldwork events (Akce) are supported at the time.

### Key Features

* **Spatial Querying:** Option to filter records based on the current map canvas extent (Bounding Box).
* **Advanced Attribute Filtering:** Supports multi-criteria filtering using controlled vocabularies (Cadastral Area, District, Period, Type of Fieldwork event, Organization, Fieldwork Manager).
* **Dynamic Geometry Retrieval:** Automatically downloads and categorizes spatial data into Point, Line, and Polygon layers.
* **Semantic Interoperability:** Automatically translates internal system codes into human-readable labels using the AIS CR API.

---

## 2. Installation Guide

1. Obtain the [plugin distribution package](https://github.com/ARUP-CAS/aiscr-qgis-amcr-viewer/archive/refs/heads/main.zip) (ZIP archive containing the `amcr_viewer` directory).
2. Launch QGIS.
3. Navigate to **Plugins**  **Manage and Install Plugins...**
4. Select the **Install from ZIP** tab.
5. Locate the source ZIP file and click **Install Plugin**.
6. Upon successful installation, the AMCR download button (load AMCR data) will appear in the interface.  

**OR**  

Install the plugin from QGIS plugin repository.

---

## 3. User Manual

### 3.1 Data Retrieval

To initiate a search query, click the **Load AMCR Data** icon. The filter dialog provides the following options:

* **Spatial Filter:** *Checkbox "Limit search to current map extent":* If checked, the query is restricted to the geographical area currently visible in the QGIS canvas. If unchecked, the query searches the entire database (use with caution regarding data volume).
* It is possible to view only those Fieldwork events with positive outcome, if "Positive findings only" is checked. Only PIANs marked as (or rather PIANs belonging to Documentation units marked as) "Type of evidence" = "positive" are rendered.


* **Attribute Filters:**
  * The dialog utilizes "Picker" widgets for controlled vocabularies (Region, District, Cadastral area, Organisation, Period, Activity Area).
  * Click **Select...** to open a searchable selection window. Multiple values can be selected simultaneously (Logic: OR).


* **Fieldwork Manager (Dynamic List):**
  * Due to the dynamic nature of the persons database, the list of Fieldwork Managers is retrieved from the AIS CR servers and needs to be updated the first time (and subsequently, if there is need).
  * To refresh the list from the server, click the **Refresh (🔄)** button next to the selection field. This downloads the latest list of researchers from the API.
* If no filter is used, all accessible Fieldwork events/PIANs are returned (although the number of Fieldwork events to be loaded is capped at 20000 records; it is advisable to set at least one filter).



### 3.2 Layer Structure & Attributes

Upon successful retrieval, the plugin generates three temporary memory layers:

1. **AMCR Plochy (Polygons)**
2. **AMČR Linie (Lines)**
3. **AMČR Body (Points)**

The Attribute Table includes standardized fields such as:

* **Identification:** `Identifikátor` (Fieldwork event ID), `PIAN` (PIAN ID).
* **Classification:** `Hlavní typ` (Main Fieldwork event Type), `Vedlejší typ` (Secondary Fieldwork event Type), `PIAN – typ` (PIAN Type).
* **Administration:** `Vedoucí akce` (Fieldwork Manager), `Organizace` (Organization), `Datum zahájeni`/`Datum ukončení` (Dates of start and end of the Fieldwork event).
* **Location:** `Katastr` (Main Cadastral area), `Další katastry` (Other Cadastral areas), `Okres` (District), `Definiční bod(y)` (PIAN point localization).
* **Links:** `Odkaz do Digiarchivu` (Direct URL to the DigiArchive record).

---

## 4. Technical Architecture

The plugin is developed in **Python 3** using the **PyQt5** framework for the GUI and the **Requests** library for HTTP communication.

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
* Parameters: `entity=akce`, `fl` (field list), `q` (query), `rows/page` (pagination).
* Logic: The plugin implements a `while True` loop to handle pagination, processing data in batches of 500 records to ensure stability.


2. **Translation API:**
* Endpoint: `https://digiarchiv.aiscr.cz/api/assets/i18n/cs.json`
* Function: Retrieves the mapping between system codes (e.g., `HES-xxxx`) and Czech labels. This dictionary is cached in memory during the session.


### 4.3 Data Persistence

* **Vocabularies:** Static vocabularies (e.g., Periods, Regions) are stored in `codelists/heslar.csv`.
* **Dynamic Data:** The list of investigators is downloaded on-demand and cached in `codelists/vedouci.csv`.
* **Layers:** Output layers are created as `memory` layers. They are non-persistent and will be lost if QGIS is closed without saving.

### 4.4 Constraints

* **Record Limit:** A safety cap of 20,000 records is enforced to prevent memory overflow in QGIS.
* **Batch Processing:** Geometry fetching is batched (50 IDs per request) to comply with URL length limitations and server load balancing.

## 6. Links and resources

* [AMCR/Digiarchive Documentation](https://amcr-help.aiscr.cz/) (only in Czech).