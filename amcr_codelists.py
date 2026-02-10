# -*- coding: utf-8 -*-
import os
import csv
import codecs
import requests
import json

# Cesta k adresáři pluginu
PLUGIN_DIR = os.path.dirname(__file__)
CODELISTS_DIR = os.path.join(PLUGIN_DIR, 'codelists')

def ensure_codelists_dir():
    if not os.path.exists(CODELISTS_DIR):
        os.makedirs(CODELISTS_DIR)

# --- 1. NAČÍTÁNÍ DAT ---

def load_csv_data(filename):
    """Obecná funkce pro načtení CSV souboru do slovníku"""
    data = {}
    path = os.path.join(CODELISTS_DIR, filename)
    if not os.path.exists(path):
        return data

    try:
        with codecs.open(path, 'r', 'utf-8') as f:
            reader = csv.reader(f, delimiter=';')
            # Zkusíme přeskočit hlavičku, pokud tam je
            first_row = next(reader, None)
            
            # Pokud soubor není prázdný, zpracujeme ho
            if first_row:
                # Pokud první řádek vypadá jako data (neobsahuje slovo "Název"), vrátíme ho do hry
                # Ale my budeme generovat soubory s hlavičkou, takže OK.
                pass 

            for row in reader:
                if len(row) >= 3:
                    label = row[0].strip()
                    code = row[1].strip()
                    category = row[2].strip()
                    
                    # Tady můžeme filtrovat podle kategorie, 
                    # nebo prostě vrátit všechno jako {label: code}
                    # Pro jednoduchost vracíme {label: code}
                    clean_code = code if code else None
                    data[label] = clean_code
    except Exception as e:
        print(f"AMČR Chyba čtení {filename}: {e}")
        
    return data

def load_all_data():
    """
    Načte statický heslář I dynamický heslář vedoucích.
    Vrací slovník slovníků.
    """
    ensure_codelists_dir()
    
    # 1. Načteme hlavní statický heslář
    # Musíme ho rozparsovat podle kategorií, tak jak to bylo předtím
    categorized_data = {
        'obdobi': {}, 'typ_akce': {}, 'areal': {}, 
        'kraj': {}, 'organizace': {}, 'okres': {}, 'katastr': {},
        'vedouci': {} 
    }
    
    # Funkce pro roztřídění načteného slovníku (tohle je trochu redundance, ale pro zachování logiky)
    def parse_file(filename):
        path = os.path.join(CODELISTS_DIR, filename)
        if not os.path.exists(path): return
        
        try:
            with codecs.open(path, 'r', 'utf-8') as f:
                reader = csv.reader(f, delimiter=';')
                next(reader, None) # Skip header
                for row in reader:
                    if len(row) >= 3:
                        label = row[0].strip()
                        code = row[1].strip()
                        cat = row[2].strip()
                        clean = code if code else None
                        
                        if cat in categorized_data:
                            categorized_data[cat][label] = clean
        except: pass

    # Načteme soubory
    parse_file('heslar.csv') # Statické
    parse_file('vedouci.csv') # Dynamické (pokud existuje)
    
    return categorized_data

# --- 2. AKTUALIZACE DAT (DOWNLOAD) ---

def download_vedouci():
    """
    Stáhne seznam vedoucích z API (pomocí onlyFacets) a uloží do codelists/vedouci.csv.
    """
    ensure_codelists_dir()
    
    # Tvá URL + pojistka, abychom dostali všechny záznamy (limit -1)
    url = "https://digiarchiv.aiscr.cz/api/search/query?entity=akce&sort=datestamp%20desc&page=0&onlyFacets=True&rows=0"
    
    try:
        r = requests.get(url, timeout=20) # Raději delší timeout pro velký seznam
        r.raise_for_status()
        data = r.json()
        
        # Cesta k datům dle tvého JSONu:
        # {"facet_counts": { "f_vedouci": [ {"name": "Novák", ...}, ... ] }}
        vedouci_list = data.get('facet_counts', {}).get('f_vedouci', [])
        
        if not vedouci_list:
             # Zkusíme ještě alternativní cestu, kdyby API vrátilo standardní Solr strukturu
             # (facet_counts -> facet_fields -> f_vedouci)
             vedouci_list = data.get('facet_counts', {}).get('facet_fields', {}).get('f_vedouci', [])

        csv_path = os.path.join(CODELISTS_DIR, 'vedouci.csv')
        
        count = 0
        with codecs.open(csv_path, 'w', 'utf-8') as f:
            writer = csv.writer(f, delimiter=';')
            writer.writerow(['Název', 'Kód', 'Kategorie'])
            
            # NOVÁ LOGIKA PARSOVÁNÍ
            for item in vedouci_list:
                name = None
                
                # Varianta A: Položka je slovník {"name": "Jan Novák", "value": 10}
                if isinstance(item, dict):
                    name = item.get('name')
                
                # Varianta B: Položka je jen string (kdyby se API vrátilo k plochému seznamu)
                elif isinstance(item, str):
                    name = item
                
                # Pokud máme jméno a není to číslo (count), zapíšeme
                if name and not str(name).isdigit():
                    writer.writerow([name, name, 'vedouci'])
                    count += 1
                
        return True, f"Staženo {count} jmen."
        
    except Exception as e:
        return False, str(e)

# --- GLOBAL DATA ---
# Toto se načte při startu QGISu
_DATA = load_all_data()

OBDOBI = _DATA['obdobi']
TYP_AKCE = _DATA['typ_akce']
AREAL = _DATA['areal']
KRAJE = _DATA['kraj']
ORGANIZACE = _DATA['organizace']
OKRESY = _DATA['okres']
KATASTRY = _DATA['katastr']
VEDOUCI = _DATA['vedouci'] # Tady to bude zpočátku prázdné, pokud soubor neexistuje

def refresh_vedouci_cache():
    """
    Znovu načte soubor vedouci.csv a aktualizuje globální proměnnou VEDOUCI.
    Použijeme 'update', aby se zachovala reference na objekt (pokud ho dialog už používá).
    """
    temp_data = load_all_data()
    new_vedouci = temp_data['vedouci']
    
    # Vyčistíme a naplníme existující slovník (in-place update)
    VEDOUCI.clear()
    VEDOUCI.update(new_vedouci)
    return len(VEDOUCI)