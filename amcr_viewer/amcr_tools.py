# -*- coding: utf-8 -*-
from qgis.core import (QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry, 
                       QgsField, QgsCoordinateReferenceSystem, QgsCoordinateTransform,
                       QgsWkbTypes, QgsPolymorphicRelation, QgsEditorWidgetSetup, Qgis)
from qgis.utils import iface
from qgis.PyQt.QtCore import Qt, QMetaType
from qgis.PyQt.QtWidgets import QApplication
from qgis.PyQt.QtGui import QCursor
import requests
import json

# Global cache to store translated terms from the Digital Archive
TRANSLATIONS = {}

def load_translations():
    """Fetches the official Czech translation dictionary from the AISCR API."""
    global TRANSLATIONS
    if TRANSLATIONS:
         return 
    
    url = "https://digiarchiv.aiscr.cz/api/assets/i18n/cs.json"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            TRANSLATIONS = r.json()
    except Exception as e:
        print(f"Error downloading vocabulary: {e}")

def tr_code(code):
    """Translates a technical code into a human-readable string using the global cache."""
    if not code: 
        return ""
    return TRANSLATIONS.get(code, code)

def load_amcr_data(canvas, bb, filters=None, typ_dat="akce", komponenty="false"):
    """
    Main processing function:
    1. Determines search area (Bounding Box)
    2. Fetches metadata and geometries from API
    3. Creates QGIS memory layers and populates them with features
    """
    load_translations()

    # --- 1. COORDINATE TRANSFORMATION ---
    # Get current map extent and transform it from project CRS (usually S-JTSK) to WGS-84 for the API
    extent = canvas.extent()
    crs_src = canvas.mapSettings().destinationCrs()
    crs_dest = QgsCoordinateReferenceSystem("EPSG:4326")
    xform = QgsCoordinateTransform(crs_src, crs_dest, QgsProject.instance())
    extent_wgs = xform.transformBoundingBox(extent)
    
    # Format the bounding box string as required by the API: minLat,minLon,maxLat,maxLon
    bbox_str = f"{extent_wgs.yMinimum()},{extent_wgs.xMinimum()},{extent_wgs.yMaximum()},{extent_wgs.xMaximum()}"
    
    url = "https://digiarchiv.aiscr.cz/api/search/query"
    
    iface.messageBar().pushMessage("AMCR", "Hledám záznamy...", level=Qgis.MessageLevel.Info)
    QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
    
    try:
        # ==========================================
        # A) METADATA FETCHING (Fieldwork/Site)
        # ==========================================
        
        base_params = {
            "mapa": "true",
            "sort": "ident_cely asc",
            "entity": typ_dat
        }

        # Restrict search to map window if requested
        if bb == "true": 
            base_params["loc_rpt"] = bbox_str

        # Apply multi-select filters from the dialog using the ':or' syntax required by the API
        if filters:
            for key, value in filters.items():
                if not value:
                    continue
                if isinstance(value, list):
                    base_params[key] = [f"{v}:or" for v in value]
                else:
                    base_params[key] = str(value).strip()

        docs = []
        current_page = 0 
        BATCH_DOCS = 500   # Records per API request
        MAX_LIMIT = 20000  # Safety limit to prevent QGIS from freezing
        feats_k = []       # List for component features (non-spatial)
        
        seen_ids = set()
        target_pian_ids_count = 0

        # Check if we should skip negative results based on filter
        skip_negativni = filters.get('posevidence') == 'true' if filters else False
        
        # --- API PAGINATION LOOP ---
        while True:
            base_params['rows'] = BATCH_DOCS
            if current_page > 0:
                base_params['page'] = current_page
            elif 'page' in base_params:
                del base_params['page']
            
            try:
                resp_docs = requests.get(url, params=base_params, timeout=30)
                resp_json = resp_docs.json()
                data = resp_json.get('response', {})
                batch_docs = data.get('docs', [])
                num_found = data.get('numFound', 0) 
                
                if not batch_docs:
                    break
                
                # Filter out duplicates and append to main list
                new_docs = []
                for d in batch_docs:
                    ident = d.get('ident_cely')
                    if ident and ident not in seen_ids:
                        seen_ids.add(ident)
                        new_docs.append(d)
                
                docs.extend(new_docs)
                print(f"Strana {current_page} stažena. Celkem záznamů: {len(docs)} / {num_found}")

                if len(docs) >= num_found:
                    break
                if len(docs) >= MAX_LIMIT:
                    iface.messageBar().pushMessage("AMCR", f"Limit {MAX_LIMIT} záznamů dosažen.", level=Qgis.MessageLevel.Warning)
                    break
                
                current_page += 1
                QApplication.processEvents() # Keep UI responsive
                
            except Exception as e:
                print(f"Chyba při stránkování na straně {current_page}: {e}")
                break

        if not docs:
             iface.messageBar().pushMessage("AMCR", "Žádné záznamy nenalezeny.", level=Qgis.MessageLevel.Warning)
             return

        # ==========================================
        # B) ATTRIBUTE PARSING
        # ==========================================
        
        # pian_lookup maps a Geometry ID (PIAN) to a list of its associated metadata
        pian_lookup = {}
        komponenty_lookup = {}
        target_pian_ids = set()
        actions_with_geom = 0
        
        # Helper function for safe single-value extraction
        def g(doc, key, default=""): 
            val = doc.get(key)
            if isinstance(val, list):
                return str(val[0]) if val else default
            return str(val) if val is not None else default

        # Helper function for safe list-value extraction and joining
        def g_list(doc, key, translate=False):
            val = doc.get(key, [])
            if not isinstance(val, list):
                val = [val] if val else []
            if translate:
                return ", ".join([tr_code(str(x)) for x in val if x])
            return ", ".join([str(x) for x in val if x])

        # Process each downloaded metadata record
        for doc in docs:
            piani = doc.get('az_dj_pian', [])
            if not piani:
                continue

            actions_with_geom += 1
            
            # Extract protected data (fields not available in public Solr index)
            az_chranene = doc.get('az_chranene_udaje', {})
            chranene = doc.get('akce_chranene_udaje') or doc.get('lokalita_chranene_udaje') or {}
            
            # Format additional cadastral areas from dictionaries
            dalsi_kat = az_chranene.get('dalsi_katastr', [])
            dalsi_kat_str = ""
            if isinstance(dalsi_kat, list):
                items = [x.get('value', '') if isinstance(x, dict) else str(x) for x in dalsi_kat]
                dalsi_kat_str = ", ".join([i for i in items if i])

            lokalizace = chranene.get('lokalizace_okolnosti', "")
            lokalita_nazev = chranene.get('nazev', "")
            lokalita_popis = chranene.get('popis', "")

            # Core metadata structure
            meta = {
                "ident_cely": doc.get('ident_cely', ''),
                "az_okres": g(doc, 'az_okres'),
                "katastr": g_list(doc, 'katastr'),
                "dalsi_katastr": dalsi_kat_str,                
                "pristupnost": g(doc, 'pristupnost'),
                "loc": g_list(doc, 'loc')
            }

            # Add entity-specific metadata
            if typ_dat == "akce":
                meta.update({
                    "akce_hlavni_vedouci": g(doc, 'akce_hlavni_vedouci'),
                    "akce_organizace": tr_code(g(doc, 'akce_organizace')),
                    "akce_specifikace_data": tr_code(g(doc, 'akce_specifikace_data')),
                    "akce_datum_zahajeni": g(doc, 'akce_datum_zahajeni'),
                    "akce_datum_ukonceni": g(doc, 'akce_datum_ukonceni'),
                    "akce_hlavni_typ": tr_code(g(doc, 'akce_hlavni_typ')),
                    "akce_vedlejsi_typ": g_list(doc, 'akce_vedlejsi_typ', translate=True),
                    "lokalizace_okolnosti": str(lokalizace) if lokalizace else "",
                    "akce_je_nz": "Ano" if doc.get('akce_je_nz') is True else "Ne",
                })

            elif typ_dat == "lokalita":
                meta.update({
                    "lokalita_nazev": lokalita_nazev,
                    "lokalita_popis": lokalita_popis,
                    "lokalita_zachovalost": tr_code(g(doc, 'lokalita_zachovalost')),
                    "lokalita_druh": tr_code(g(doc, 'lokalita_druh')),
                    "lokalita_typ": tr_code(g(doc, 'lokalita_typ_lokality')),
                })
            
            # Documentation units (DJ) within the record
            djs = doc.get('az_dokumentacni_jednotka', [])

            for dj in djs:
                # Filter out negative evidence units if requested
                if skip_negativni and dj.get('dj_negativni_jednotka') is True:
                    continue

                dj_id = dj.get('ident_cely')
                dj_typ = dj.get('dj_typ')

                # Merge general meta with documentation unit specific data
                dj_meta = {
                    **meta,
                    'dj_id': dj_id,
                    'dj_typ_value': dj_typ.get('value') if dj_typ else "",
                    'dj_negativni': "Negativní" if dj.get('dj_negativni_jednotka') is True else "Pozitivní"
                }
                
                # Link Documentation Unit to Geometry (PIAN)
                dj_pian = dj.get('dj_pian')
                if dj_pian:
                    dj_pian_value = dj_pian.get('id')
                    if dj_pian_value:
                        target_pian_ids.add(dj_pian_value)
                        target_pian_ids_count += 1
                        if dj_pian_value not in pian_lookup:
                            pian_lookup[dj_pian_value] = []
                        pian_lookup[dj_pian_value].append(dj_meta)

                        # Parse non-spatial components if requested (for relational tables)
                        if komponenty == "true":
                            komps = dj.get('dj_komponenta', [])
                            for komp in komps:
                                komp_temp = [
                                    komp.get('ident_cely', ""),
                                    komp.get('komponenta_areal', {}).get('value', ""),
                                    komp.get('komponenta_obdobi', {}).get('value', "")
                                ]
                                if dj_id not in komponenty_lookup:
                                    komponenty_lookup[dj_id] = []
                                komponenty_lookup[dj_id].append(komp_temp)


        if not target_pian_ids:
            iface.messageBar().pushMessage("AMCR", f"Nalezeno {len(docs)} záznamů, ale žádný nemá geometrii.", level=Qgis.MessageLevel.Warning)
            return        


        # ==========================================
        # C) GEOMETRY FETCHING (PIAN)
        # ==========================================
        ids_list = list(target_pian_ids)
        total_pians = len(ids_list)
        docs_pian = []
        BATCH_PIAN = 200 # Geometry requests are batch-processed to stay under URL length limits
        
        iface.messageBar().pushMessage("AMCR", f"Záznamů: {len(docs)} (z toho {actions_with_geom} s mapou). Stahuji {total_pians} unikátních geometrií, vykresluji {target_pian_ids_count} geometrií...", level=Qgis.MessageLevel.Info)
        
        fl_pian = ["ident_cely", "pian_typ", "pian_chranene_udaje", "pian_presnost"]

        for i in range(0, total_pians, BATCH_PIAN):
            batch = ids_list[i : i + BATCH_PIAN]
            or_query = " OR ".join(batch)
            fq_pian = f"ident_cely:({or_query})"
            
            params_pian = {
                "mapa": "true",
                "entity": "pian",
                "q": fq_pian,
                "rows": len(batch),
                "fl": ",".join(fl_pian)
            }
            try:
                QApplication.processEvents() 
                r_pian = requests.get(url, params=params_pian, timeout=15)
                batch_docs = r_pian.json().get('response', {}).get('docs', [])
                docs_pian.extend(batch_docs)
            except Exception as e:
                print(f"Chyba PIAN: {e}")

        # ==========================================
        # D) LAYER CREATION (QGIS Memory Layers)
        # ==========================================
        
        archeologicky_zaznam = "Akce" if typ_dat == "akce" else "Lokalita"

        # Initialize three layers for different geometry types (S-JTSK CRS)
        vl_poly = QgsVectorLayer("Polygon?crs=epsg:5514", f"AMCR_{archeologicky_zaznam}_Polygony", "memory")
        vl_line = QgsVectorLayer("LineString?crs=epsg:5514", f"AMCR_{archeologicky_zaznam}_Linie", "memory")
        vl_point = QgsVectorLayer("Point?crs=epsg:5514", f"AMCR_{archeologicky_zaznam}_Body", "memory")
        layers = [vl_poly, vl_line, vl_point]

        # Define attribute table structure
        cols = [
            QgsField("pian", QMetaType.Type.QString),
            QgsField("presnost", QMetaType.Type.QString),
            QgsField("pian_typ", QMetaType.Type.QString),
            QgsField("dj", QMetaType.Type.QString),
            QgsField("typ_dj", QMetaType.Type.QString),
            QgsField("definicni_body", QMetaType.Type.QString),
            QgsField(typ_dat, QMetaType.Type.QString),
            QgsField("odkaz_do_digiarchivu", QMetaType.Type.QString),
            QgsField("okres", QMetaType.Type.QString),
            QgsField("katastr", QMetaType.Type.QString),
            QgsField("dalsi_katastry", QMetaType.Type.QString)
        ]

        # Extend table based on data type
        if typ_dat == "akce":
            cols += [
                QgsField("akce_lokalizace", QMetaType.Type.QString),
                QgsField("vedouci", QMetaType.Type.QString),
                QgsField("organizace", QMetaType.Type.QString),
                QgsField("specifikace_data", QMetaType.Type.QString),
                QgsField("zahajeni", QMetaType.Type.QString),
                QgsField("ukonceni", QMetaType.Type.QString),
                QgsField("hlavni_typ", QMetaType.Type.QString),
                QgsField("vedlejsi_typ", QMetaType.Type.QString),
                QgsField("zjisteni", QMetaType.Type.QString),                
                QgsField("nahrazuje_NZ", QMetaType.Type.QString),
            ]
        elif typ_dat == "lokalita":
            cols += [
                QgsField("nazev_lokality", QMetaType.Type.QString),
                QgsField("popis_lokality", QMetaType.Type.QString),
                QgsField("typ_lokality", QMetaType.Type.QString),
                QgsField("druh_lokality", QMetaType.Type.QString),
                QgsField("zachovalost", QMetaType.Type.QString)
            ]
        
        cols.append(QgsField("Přístupnost", QMetaType.Type.QString))

        # Use aliases for technical field names
        alias_map = {
            "pian": "PIAN",
            "presnost": "Přesnost",
            "pian_typ": "PIAN – typ",
            "dj": "Dokumentační jednotka",
            "typ_dj": "Typ dokumentační jednotky",
            "definicni_body": "Definiční bod(y) (WGS-84)",
            typ_dat: archeologicky_zaznam,
            "odkaz_do_digiarchivu": "Odkaz do Digitálního archivu AMČR",
            "okres": "Okres",
            "katastr": "Katastr",
            "dalsi_katastry": "Další katastry",
            "akce_lokalizace": "Akce – lokalizace",
            "vedouci": "Vedoucí akce",
            "organizace": "Organizace",
            "specifikace_data": "Specifikace data",
            "zahajeni": "Datum zahájeni",
            "ukonceni": "Datum ukončení",
            "hlavni_typ": "Hlavní typ",
            "vedlejsi_typ": "Vedlejší typ",
            "zjisteni": "Zjištění",
            "nahrazuje_NZ": "Akce – nahrazuje NZ",
            "nazev_lokality": "Název lokality",
            "popis_lokality": "Popis lokality",
            "typ_lokality": "Typ lokality",
            "druh_lokality": "Druh lokality",
            "zachovalost": "Zachovalost"
        }        

        # Create a non-spatial table for components if requested
        if komponenty == "true":
            vl_komponenty = QgsVectorLayer("None", "AMCR Komponenty", "memory")
            pr = vl_komponenty.dataProvider()
            komponenty_cols = [
                QgsField("komponenta", QMetaType.Type.QString),
                QgsField("dj_id", QMetaType.Type.QString),
                QgsField("komponenta_areal", QMetaType.Type.QString),
                QgsField("komponenta_obdobi", QMetaType.Type.QString),
                QgsField("vrstva", QMetaType.Type.QString)
            ]
            pr.addAttributes(komponenty_cols)
            vl_komponenty.updateFields()

            idx_vrstva = vl_komponenty.fields().indexOf("vrstva")
            vl_komponenty.setEditorWidgetSetup(idx_vrstva, QgsEditorWidgetSetup("Hidden", {}))

        for vl in layers:
            vl.dataProvider().addAttributes(cols)
            vl.updateFields()
            for tech_name, alias in alias_map.items():
                idx = vl.fields().lookupField(tech_name)
                if idx != -1:
                    vl.setFieldAlias(idx, alias)
            
        # Lists to hold features before batch-adding to layers
        feats_p, feats_l, feats_pt = [], [], []
        
        # --- FEATURE POPULATION ---
        for doc in docs_pian:
            try:
                pid = doc.get('ident_cely', '')
                if pid not in pian_lookup:
                    continue 
                                        
                metas = pian_lookup[pid]
                
                # Extract WKT geometry from protected JSON data
                raw = doc.get('pian_chranene_udaje')
                if isinstance(raw, list) and raw:
                    raw = raw[0]
                jdata = json.loads(raw) if isinstance(raw, str) else (raw or {})
                
                wkt = None
                if jdata.get('geom_sjtsk_wkt'):
                    wkt = jdata.get('geom_sjtsk_wkt', {}).get('value')
                elif jdata.get('geom_wkt'):
                    wkt = jdata.get('geom_wkt', {}).get('value')
                
                pian_presnost = tr_code(str(doc.get('pian_presnost', '')))
                pian_typ = tr_code(str(doc.get('pian_typ', '')))

                # Final precision filter check
                if filters and filters.get('f_pian_presnost') and doc.get('pian_presnost') not in filters.get('f_pian_presnost'):
                    continue

                if wkt:
                    geom = QgsGeometry.fromWkt(wkt)
                    if geom.isGeosValid():
                        t = geom.type()
                        target_list = None
                        if t == QgsWkbTypes.PolygonGeometry:
                            target_list = feats_p
                            referenced_layer = vl_poly
                        elif t == QgsWkbTypes.LineGeometry:
                            target_list = feats_l
                            referenced_layer = vl_line
                        elif t == QgsWkbTypes.PointGeometry:
                            target_list = feats_pt
                            referenced_layer = vl_point
                        
                        if target_list is None:
                            continue

                        is_akce = (typ_dat == "akce")

                        # Create a QGIS feature for each documentation unit associated with this geometry
                        for meta in metas:
                            feat = QgsFeature()
                            feat.setGeometry(geom)
                            atributy = [
                                pid, pian_presnost, pian_typ, meta['dj_id'],
                                meta['dj_typ_value'], meta['loc'], meta['ident_cely'],
                                "https://digiarchiv.aiscr.cz/id/" + meta['ident_cely'],
                                meta['az_okres'], meta['katastr'], meta['dalsi_katastr']
                            ]
                            if is_akce:
                                atributy.extend([
                                    meta['lokalizace_okolnosti'], meta['akce_hlavni_vedouci'],
                                    meta['akce_organizace'], meta['akce_specifikace_data'],
                                    meta['akce_datum_zahajeni'], meta['akce_datum_ukonceni'],
                                    meta['akce_hlavni_typ'], meta['akce_vedlejsi_typ'],
                                    meta['dj_negativni'], meta['akce_je_nz']
                                ])
                            else:
                                atributy.extend([
                                    meta['lokalita_nazev'], meta['lokalita_popis'],
                                    meta['lokalita_typ'], meta['lokalita_druh'],
                                    meta['lokalita_zachovalost']
                                ])
                            
                            if komponenty == "true" and meta['dj_id'] in komponenty_lookup:
                                for k in komponenty_lookup[meta['dj_id']]:
                                    if len(k) == 3:
                                        k.append(referenced_layer.id())
                            
                            atributy.append(meta['pristupnost'])
                            feat.setAttributes(atributy)
                            target_list.append(feat)
                            
            except Exception as ex:
                print(f"Chyba při tvorbě feature: {ex}")
                pass
        
        if komponenty == "true":
            for k in komponenty_lookup:
                for komp in komponenty_lookup[k]:
                    if len(komp) == 4:
                        feat = QgsFeature()
                        atributy = [
                            komp[0], k, komp[1], komp[2], komp[3]
                        ]
                        feat.setAttributes(atributy)
                        feats_k.append(feat)

        # --- ADDING TO QGIS INTERFACE ---
        proj = QgsProject.instance()
        added = 0
        layers_to_process = [
            (feats_p, vl_poly, "Polygony"), 
            (feats_l, vl_line, "Linie"), 
            (feats_pt, vl_point, "Body"),
        ]

        if komponenty == "true":
            layers_to_process.append((feats_k, vl_komponenty, "Komponenty"))

        for f, l, n in layers_to_process:
            if f:
                l.dataProvider().addFeatures(f)
                l.updateExtents()
                l.setName(f"AMCR_{archeologicky_zaznam}_{n}") 
                proj.addMapLayer(l)
                if n != "Komponenty":
                    added += len(f)
        
        if added > 0:
            iface.messageBar().pushMessage("AMCR", f"Hotovo. Záznamů: {len(docs)} (s geom: {actions_with_geom}). Vykresleno: {added} prvků.", level=Qgis.MessageLevel.Success)

            # --- RELATIONSHIP MANAGEMENT ---
            # Set up automatic links between spatial layers and the component table
            if komponenty == "true":
                parent_layers_ids = []
                if feats_p:
                    parent_layers_ids.append(vl_poly.id())
                if feats_l:
                    parent_layers_ids.append(vl_line.id())
                if feats_pt:
                    parent_layers_ids.append(vl_point.id())

                rel_manager = proj.relationManager()
                
                rel = QgsPolymorphicRelation()
                # rel.setId(f"rel_komponenty_{archeologicky_zaznam}") 
                rel.setName("Komponenty")                    
                rel.setReferencingLayer(vl_komponenty.id())
                rel.setReferencedLayerExpression("@layer_id")
                rel.setReferencedLayerField("vrstva")
                rel.setReferencedLayerIds(parent_layers_ids)
                rel.addFieldPair("dj_id", "Dokumentační jednotka")
                rel.generateId() 
                
                if rel.isValid():
                    rel_manager.addPolymorphicRelation(rel)
                else:
                    print("Relace Komponenty není validní!")

        else:
            iface.messageBar().pushMessage("AMCR", "Žádná data k zobrazení.", level=Qgis.MessageLevel.Info)

    except Exception as e:
        iface.messageBar().pushMessage("Chyba", str(e), level=Qgis.MessageLevel.Critical)
    finally:
        # Always restore cursor, even after failure
        QApplication.restoreOverrideCursor()