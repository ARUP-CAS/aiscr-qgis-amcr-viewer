# -*- coding: utf-8 -*-
import os
import csv
import requests

# Cesta k adresáři pluginu
PLUGIN_DIR = os.path.dirname(__file__)
CODELISTS_DIR = os.path.join(PLUGIN_DIR, 'codelists')

def ensure_codelists_dir():
    if not os.path.exists(CODELISTS_DIR):
        os.makedirs(CODELISTS_DIR)

# --- 1. NAČÍTÁNÍ DAT ---

def parse_codelist_file(filename, target_dict=None):
    """Univerzální funkce pro načtení CSV a jeho roztřídění podle kategorií."""
    if target_dict is None:
        target_dict = {}
        
    path = os.path.join(CODELISTS_DIR, filename)
    if not os.path.exists(path): 
        return target_dict
        
    try:
        # Moderní Python 3 otevírání souborů
        with open(path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f, delimiter=';')
            next(reader, None) # Skip header
            for row in reader:
                if len(row) >= 3:
                    label = row[0].strip()
                    code = row[1].strip()
                    cat = row[2].strip()
                    clean = code if code else None
                    
                    # Pokud kategorie ještě neexistuje, vytvoříme pro ni prázdný slovník
                    if cat not in target_dict:
                        target_dict[cat] = {}
                        
                    target_dict[cat][label] = clean
    except Exception as e:
        print(f"AMČR Chyba čtení {filename}: {e}")
        
    return target_dict

def load_all_data():
    """Načte statický i dynamický heslář při startu pluginu."""
    ensure_codelists_dir()
    
    # Prázdné struktury jako základ
    categorized_data = {
        'obdobi': {}, 'typ_akce': {}, 'areal': {}, 
        'kraj': {}, 'organizace': {}, 'okres': {}, 'katastr': {},
        'vedouci': {}, 'pian_presnost': {}, 'typ_lokality': {}, 'druh_lokality': {},
        'jistota': {}, 'lokalita_zachovalost': {}
    }
    
    # Načteme soubory a naplníme slovník
    parse_codelist_file('heslar.csv', categorized_data)
    parse_codelist_file('vedouci.csv', categorized_data)
    
    return categorized_data

# --- 2. AKTUALIZACE DAT (DOWNLOAD) ---

def download_vedouci():
    """Stáhne seznam vedoucích z API a uloží do codelists/vedouci.csv."""
    ensure_codelists_dir()
    
    url = "https://digiarchiv.aiscr.cz/api/search/query?entity=akce&sort=datestamp%20desc&page=0&onlyFacets=True&rows=0"
    
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        data = r.json()
        
        vedouci_list = data.get('facet_counts', {}).get('f_vedouci', [])
        if not vedouci_list:
             vedouci_list = data.get('facet_counts', {}).get('facet_fields', {}).get('f_vedouci', [])

        csv_path = os.path.join(CODELISTS_DIR, 'vedouci.csv')
        
        count = 0
        # Použití standardního open() s newline='', což zabraňuje prázdným řádkům ve Windows
        with open(csv_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f, delimiter=';')
            writer.writerow(['Název', 'Kód', 'Kategorie'])
            
            for item in vedouci_list:
                name = None
                if isinstance(item, dict):
                    name = item.get('name')
                elif isinstance(item, str):
                    name = item
                
                if name and not str(name).isdigit():
                    writer.writerow([name, name, 'vedouci'])
                    count += 1
                
        return True, f"Staženo {count} jmen."
        
    except Exception as e:
        return False, str(e)

# --- GLOBAL DATA ---
_DATA = load_all_data()

# Používáme .get(), aby to nespadlo, pokud by nějaká kategorie v CSV úplně chyběla
OBDOBI = _DATA.get('obdobi', {})
TYP_AKCE = _DATA.get('typ_akce', {})
AREAL = _DATA.get('areal', {})
KRAJE = _DATA.get('kraj', {})
ORGANIZACE = _DATA.get('organizace', {})
OKRESY = _DATA.get('okres', {})
KATASTRY = _DATA.get('katastr', {})
VEDOUCI = _DATA.get('vedouci', {})
PIAN_PRESNOST = _DATA.get('pian_presnost', {})
TYP_LOKALITY = _DATA.get('typ_lokality', {})
DRUH_LOKALITY = _DATA.get('druh_lokality', {})
JISTOTA = _DATA.get('jistota', {})
LOKALITA_ZACHOVALOST = _DATA.get('lokalita_zachovalost', {})

def refresh_vedouci_cache():
    """Znovu načte POUZE soubor vedouci.csv, což je 100x rychlejší."""
    # Parsujeme jen soubor s vedoucími (zbytek nás nezajímá)
    temp_data = parse_codelist_file('vedouci.csv')
    new_vedouci = temp_data.get('vedouci', {})
    
    # Aktualizujeme globální slovník
    VEDOUCI.clear()
    VEDOUCI.update(new_vedouci)
    return len(VEDOUCI)