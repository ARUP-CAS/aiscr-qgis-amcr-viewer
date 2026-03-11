# -*- coding: utf-8 -*-
import os
import csv
import requests

# Define paths for the plugin and its codelists directory
PLUGIN_DIR = os.path.dirname(__file__)
CODELISTS_DIR = os.path.join(PLUGIN_DIR, 'codelists')

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
        print(f"AMČR Codelist Read Error for {filename}: {e}")
        
    return target_dict

def load_all_data():
    """Loads all static and dynamic codelists during plugin startup."""
    ensure_codelists_dir()
    
    # Initialize the base structure with empty dictionaries for all expected categories
    categorized_data = {
        'obdobi': {}, 'typ_akce': {}, 'areal': {}, 
        'kraj': {}, 'organizace': {}, 'okres': {}, 'katastr': {},
        'vedouci': {}, 'pian_presnost': {}, 'typ_lokality': {}, 'druh_lokality': {},
        'jistota': {}, 'lokalita_zachovalost': {}
    }
    
    # Parse the default static codelist and the dynamically generated leaders codelist
    parse_codelist_file('heslar.csv', categorized_data)
    parse_codelist_file('vedouci.csv', categorized_data)
    
    return categorized_data

def download_vedouci():
    """Fetches the list of leaders from the AMČR API and saves it to a CSV file."""
    ensure_codelists_dir()
    
    # API endpoint for fetching facet data for leaders
    url = "https://digiarchiv.aiscr.cz/api/search/query?entity=akce&sort=datestamp%20desc&page=0&onlyFacets=True&rows=0"
    
    try:
        # Execute the GET request with a 20-second timeout
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        data = r.json()
        
        # Extract the leaders list from the JSON response using safe dict getters
        vedouci_list = data.get('facet_counts', {}).get('f_vedouci', [])
        if not vedouci_list:
             vedouci_list = data.get('facet_counts', {}).get('facet_fields', {}).get('f_vedouci', [])

        csv_path = os.path.join(CODELISTS_DIR, 'vedouci.csv')
        
        count = 0
        
        # Open the target CSV file for writing without extra blank lines
        with open(csv_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f, delimiter=';')
            
            # Write the standard header required by the parser function
            writer.writerow(['Název', 'Kód', 'Kategorie'])
            
            # Iterate through the API results and format them for the CSV
            for item in vedouci_list:
                name = None
                if isinstance(item, dict):
                    name = item.get('name')
                elif isinstance(item, str):
                    name = item
                
                # Ignore pure numbers (which are usually counts) and write valid names
                if name and not str(name).isdigit():
                    writer.writerow([name, name, 'vedouci'])
                    count += 1
                
        return True, f"Staženo {count} jmen."
        
    except Exception as e:
        return False, str(e)

# Initialize global codelist data when the module is imported
_DATA = load_all_data()

# Safely extract individual categories into global variables for easy access across the plugin
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
    """Reloads only the 'vedouci.csv' file to quickly update the cache without full initialization."""
    # Parse only the targeted file containing the updated leaders
    temp_data = parse_codelist_file('vedouci.csv')
    new_vedouci = temp_data.get('vedouci', {})
    
    # Clear the existing global dictionary and update it with the fresh data
    VEDOUCI.clear()
    VEDOUCI.update(new_vedouci)
    
    return len(VEDOUCI)