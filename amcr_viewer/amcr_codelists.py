# -*- coding: utf-8 -*-
import os
import csv
import requests
import xml.etree.ElementTree as ET
import time
from qgis.core import QgsMessageLog, Qgis

# Define paths for the plugin and its codelists directory
PLUGIN_DIR = os.path.dirname(__file__)
CODELISTS_DIR = os.path.join(PLUGIN_DIR, 'codelists')
BASE_URL = "https://api.aiscr.cz/2.2/oai"
OUTPUT_FILE = os.path.join(CODELISTS_DIR, 'heslar.csv')

slovnicek = {
    'obdobi' : 'heslo:obdobi',
    'typ_akce' : 'heslo:akce_typ',
    'areal' : 'heslo:areal',    
    'kraj' : 'ruian_kraj',
    'organizace' : 'organizace',
    'okres' : 'ruian_okres',
    'katastr' : 'ruian_katastr',
    'vedouci' : 'osoba',
    'pian_presnost' : 'heslo:pian_presnost',
    'typ_lokality' : 'heslo:lokalita_typ',
    'druh_lokality' : 'heslo:lokalita_druh',
    'jistota' : 'heslo:jistota_urceni',
    'lokalita_zachovalost' : 'heslo:stav_dochovani'
}

NS = {
    'oai': 'http://www.openarchives.org/OAI/2.0/',
    'dc': 'http://purl.org/dc/elements/1.1/',
    'oai_dc': 'http://www.openarchives.org/OAI/2.0/oai_dc/'
}

def ensure_codelists_dir():
    """Creates the codelists directory if it does not exist."""
    if not os.path.exists(CODELISTS_DIR):
        os.makedirs(CODELISTS_DIR)

def parse_codelist_file(filename, target_dict=None):
    """Reads a CSV codelist file and populates the target dictionary grouped by categories."""
    if target_dict is None:
        target_dict = {}
        
    path = os.path.join(CODELISTS_DIR, filename)
    
    # Return early if the file doesn't exist to avoid missing file errors
    if not os.path.exists(path): 
        return target_dict
        
    try:
        # Open the file using standard UTF-8 encoding
        with open(path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f, delimiter=';')
            
            # Skip the CSV header row
            next(reader, None) 
            
            # Iterate through rows and extract label, code, and category
            for row in reader:
                if len(row) >= 3:
                    label = row[0].strip()
                    code = row[1].strip()
                    cat = row[2].strip()
                    clean = code if code else None
                    
                    # Initialize a new dictionary for a category if encountered for the first time
                    if cat not in target_dict:
                        target_dict[cat] = {}
                        
                    # Assign the extracted code to the corresponding label within the category
                    target_dict[cat][label] = clean
    except Exception as e:
        QgsMessageLog.logMessage(f"AMČR Codelist Read Error for {filename}: {e}", "AMČR", Qgis.Critical)
        
    return target_dict

def load_all_data():
    """Loads all static and dynamic codelists during plugin startup."""
    ensure_codelists_dir()
    categorized_data = {k: {} for k in slovnicek.keys()}
    parse_codelist_file('heslar.csv', categorized_data)
    return categorized_data

def fetch_set(internal_name, api_set, task=None):
    dataset = []
    params = {
        "verb": "ListRecords",
        "metadataPrefix": "oai_dc",
        "set": api_set
    }
    
    while True:
        # Kontrola zrušení v každém kroku
        if task and task.isCanceled():
            return None

        try:
            response = requests.get(BASE_URL, params=params, timeout=30)
            response.raise_for_status()
            root = ET.fromstring(response.content)
            
            records = root.findall('.//oai:record', NS)
            for rec in records:
                metadata = rec.find('.//oai_dc:dc', NS)
                if metadata is not None:
                    # Kód (identifier)
                    kod = metadata.find('dc:identifier', NS).text if metadata.find('dc:identifier', NS) is not None else ""
                    
                    # Název (title) - filtrujeme systémové popisky "AMČR - ..."
                    titles = metadata.findall('dc:title', NS)
                    nazev = ""
                    for t in titles:
                        if t.text and not t.text.startswith("AMČR -") and not t.text.startswith(" AMČR -"):
                            nazev = t.text
                            break
                    # Pokud by náhodou žádný title neprošel filtrem, vezmeme první dostupný
                    if not nazev and titles:
                        nazev = titles[0].text
                    
                    specialni_pripady = ['okres', 'katastr']

                    if internal_name in specialni_pripady:
                        kod = nazev

                    dataset.append({
                        'Název': nazev,
                        'Kód': kod,
                        'Kategorie': internal_name
                    })

            # Stránkování
            token = root.find('.//oai:resumptionToken', NS)
            if token is not None and token.text:
                params = {
                    "verb": "ListRecords",
                    "resumptionToken": token.text
                }
                time.sleep(0.5)
            else:
                break
                
        except Exception as e:
            QgsMessageLog.logMessage(f"Chyba u setu {api_set}: {e}", "AMČR", Qgis.Warning)
            break
            
    return dataset

def download_heslare(task=None):
    """Fetches the codelists from the AMČR API and saves it to a CSV file."""
    ensure_codelists_dir()
    all_data = []
    total_sets = len(slovnicek)
    
    for index, (interni, api_nazev) in enumerate(slovnicek.items()):
        # Pokud uživatel task zrušil v liště QGISu
        if task and task.isCanceled():
            return False

        QgsMessageLog.logMessage(f"Zpracovávám kategorii: {interni}...", "AMČR", Qgis.Info)
        
        # Nyní předáváme task správně do upravené funkce
        data = fetch_set(interni, api_nazev, task=task)
        
        if data is None:
            return False # Bylo zrušeno uprostřed stahování

        all_data.extend(data)

        # Reportování postupu (0-100)
        if task:
            progress = (index + 1) / total_sets * 100
            task.setProgress(progress)

    # Uložení do CSV
    with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8-sig') as f:
        fieldnames = ['Název', 'Kód', 'Kategorie']
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=';')
        writer.writeheader()
        writer.writerows(all_data)

    return True

def refresh_globals():
    """Znovu načte data ze souborů do globálních proměnných."""
    global OBDOBI, TYP_AKCE, AREAL, KRAJE, ORGANIZACE, OKRESY, KATASTRY
    global VEDOUCI, PIAN_PRESNOST, TYP_LOKALITY, DRUH_LOKALITY, JISTOTA, LOKALITA_ZACHOVALOST
    
    data = load_all_data()
    
    OBDOBI.clear()
    OBDOBI.update(data.get('obdobi', {}))
    TYP_AKCE.clear()
    TYP_AKCE.update(data.get('typ_akce', {}))
    AREAL.clear()
    AREAL.update(data.get('areal', {}))
    KRAJE.clear()
    KRAJE.update(data.get('kraj', {}))
    ORGANIZACE.clear()
    ORGANIZACE.update(data.get('organizace', {}))
    OKRESY.clear()
    OKRESY.update(data.get('okres', {}))
    KATASTRY.clear()
    KATASTRY.update(data.get('katastr', {}))
    VEDOUCI.clear()
    VEDOUCI.update(data.get('vedouci', {}))
    PIAN_PRESNOST.clear()
    PIAN_PRESNOST.update(data.get('pian_presnost', {}))
    TYP_LOKALITY.clear()
    TYP_LOKALITY.update(data.get('typ_lokality', {}))
    DRUH_LOKALITY.clear()
    DRUH_LOKALITY.update(data.get('druh_lokality', {}))
    JISTOTA.clear()
    JISTOTA.update(data.get('jistota', {}))
    LOKALITA_ZACHOVALOST.clear()
    LOKALITA_ZACHOVALOST.update(data.get('lokalita_zachovalost', {}))

# Inicializace prázdných diktů, které se naplní hned pod tím
OBDOBI = {}
TYP_AKCE = {}
AREAL = {}
KRAJE = {}
ORGANIZACE = {}
OKRESY = {}
KATASTRY = {}
VEDOUCI = {}
PIAN_PRESNOST = {}
TYP_LOKALITY = {}
DRUH_LOKALITY = {}
JISTOTA = {}
LOKALITA_ZACHOVALOST = {}

refresh_globals()