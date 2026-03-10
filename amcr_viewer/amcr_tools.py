# -*- coding: utf-8 -*-
from qgis.gui import QgsMapToolIdentifyFeature
from qgis.core import (QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry, 
                       QgsField, QgsCoordinateReferenceSystem, QgsCoordinateTransform,
                       QgsWkbTypes, QgsRelation, QgsEditorWidgetSetup)
from qgis.utils import iface
from qgis.PyQt.QtCore import QVariant, Qt
from qgis.PyQt.QtWidgets import QMessageBox, QApplication
import requests
import json
import xml.etree.ElementTree as ET
import re

# Global translations cache
TRANSLATIONS = {}

# Download Digiarchive's vocabulary
def load_translations():
    global TRANSLATIONS
    if TRANSLATIONS:
         return 
    
    url = "https://digiarchiv.aiscr.cz/api/assets/i18n/cs.json"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            TRANSLATIONS = r.json()
    except Exception as e:
        print(f"Chyba při stahování hesláře: {e}")

def tr_code(code):
    if not code: 
        return ""
    return TRANSLATIONS.get(code, code)

def load_amcr_data(canvas, bb, filters=None, typ_dat="akce", komponenty="false"):
    load_translations()

    # 1. Bounding box
    extent = canvas.extent()
    crs_src = canvas.mapSettings().destinationCrs()
    crs_dest = QgsCoordinateReferenceSystem("EPSG:4326")
    xform = QgsCoordinateTransform(crs_src, crs_dest, QgsProject.instance())
    extent_wgs = xform.transformBoundingBox(extent)
    bbox_str = f"{extent_wgs.yMinimum()},{extent_wgs.xMinimum()},{extent_wgs.yMaximum()},{extent_wgs.xMaximum()}"
    
    url = "https://digiarchiv.aiscr.cz/api/search/query"
    
    iface.messageBar().pushMessage("AMCR", "Hledám záznamy...", level=1)
    QApplication.setOverrideCursor(Qt.WaitCursor)
    
    try:
        # ===================
        # A) METADATA (Fieldwork event/Site)
        # ===================
        
        base_params = {
            "mapa": "true",
            "sort": "ident_cely asc"
        }

        base_params["entity"] = typ_dat

        if bb == "true": 
            base_params["loc_rpt"] = bbox_str

        # Apply filters
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
        BATCH_DOCS = 500
        MAX_LIMIT = 20000 
        feats_k = []
        
        seen_ids = set()
        target_pian_ids_count = 0
        
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
                    iface.messageBar().pushMessage("AMCR", f"Limit {MAX_LIMIT} záznamů dosažen.", level=1)
                    break
                
                current_page += 1
                QApplication.processEvents()
                
            except Exception as e:
                print(f"Chyba při stránkování na straně {current_page}: {e}")
                break

        if not docs:
             iface.messageBar().pushMessage("AMCR", "Žádné záznamy nenalezeny.", level=1)
             return

        # ==========================================
        # Attribute parsing
        # ==========================================
        pian_lookup = {}
        target_pian_ids = set()
        actions_with_geom = 0
        
        for doc in docs:
            piani = doc.get('az_dj_pian', [])
            if not piani:
                continue

            actions_with_geom += 1
            
            def g(key, default=""): 
                val = doc.get(key)
                if isinstance(val, list):
                    return str(val[0]) if val else default
                return str(val) if val is not None else default

            def g_list(key, translate=False):
                val = doc.get(key, [])
                if not isinstance(val, list):
                    val = [val] if val else []
                if translate:
                    return ", ".join([tr_code(str(x)) for x in val if x])
                return ", ".join([str(x) for x in val if x])

            az_chranene = doc.get('az_chranene_udaje', {})
            chranene = doc.get('akce_chranene_udaje') or doc.get('lokalita_chranene_udaje') or {}
            
            dalsi_kat = az_chranene.get('dalsi_katastr', [])
            dalsi_kat_str = ""
            if isinstance(dalsi_kat, list):
                items = [x.get('value', '') if isinstance(x, dict) else str(x) for x in dalsi_kat]
                dalsi_kat_str = ", ".join([i for i in items if i])

            lokalizace = chranene.get('lokalizace_okolnosti', "")
            lokalita_nazev = chranene.get('nazev', "")
            lokalita_popis = chranene.get('popis', "")

            # Prepate common metadata
            meta = {
                "ident_cely": doc.get('ident_cely', ''),
                "az_okres": g('az_okres'),
                "katastr": g_list('katastr'),
                "dalsi_katastr": dalsi_kat_str,                
                "pristupnost": g('pristupnost'),
                "loc": g_list('loc')
            }

            if typ_dat == "akce":
                meta.update({
                    "akce_hlavni_vedouci": g('akce_hlavni_vedouci'),
                    "akce_organizace": tr_code(g('akce_organizace')),
                    "akce_specifikace_data": tr_code(g('akce_specifikace_data')),
                    "akce_datum_zahajeni": g('akce_datum_zahajeni'),
                    "akce_datum_ukonceni": g('akce_datum_ukonceni'),
                    "akce_hlavni_typ": tr_code(g('akce_hlavni_typ')),
                    "akce_vedlejsi_typ": g_list('akce_vedlejsi_typ', translate=True),
                    "lokalizace_okolnosti": str(lokalizace) if lokalizace else "",
                    "akce_je_nz": "Ano" if doc.get('akce_je_nz') is True else "Ne",
                })

            elif typ_dat == "lokalita":
                meta.update({
                    "lokalita_nazev": lokalita_nazev,
                    "lokalita_popis": lokalita_popis,
                    "lokalita_zachovalost": tr_code(g('lokalita_zachovalost')),
                    "lokalita_druh": tr_code(g('lokalita_druh')),
                    "lokalita_typ": tr_code(g('lokalita_typ_lokality')),
                })
            
            djs = doc.get('az_dokumentacni_jednotka', [])

            for dj in djs:
                if filters and filters.get('posevidence') == 'true' and dj.get('dj_negativni_jednotka') is True:
                    continue

                dj_meta = meta.copy()
                dj_id = dj.get('ident_cely')
                dj_meta['dj_id'] = dj_id
                dj_typ = dj.get('dj_typ')
                dj_meta['dj_typ_value'] = dj_typ.get('value') if dj_typ else ""
                dj_meta['dj_negativni'] = "Negativní" if dj.get('dj_negativni_jednotka') is True else "Pozitivní"
                dj_pian = dj.get('dj_pian')
                if dj_pian:
                    dj_pian_value = dj_pian.get('id')
                    if dj_pian_value:
                        target_pian_ids.add(dj_pian_value)
                        target_pian_ids_count = target_pian_ids_count+1
                        if dj_pian_value not in pian_lookup:
                            pian_lookup[dj_pian_value] = []
                        pian_lookup[dj_pian_value].append(dj_meta)

                        if komponenty == "true":
                            komps = dj.get('dj_komponenta', [])
                            for komp in komps:
                                feat = QgsFeature()
                                atributy = [
                                    komp.get('ident_cely', ""),
                                    dj_id,
                                    # komponenta_aktivita ..?,
                                    komp.get('komponenta_areal', {}).get('value', ""),
                                    komp.get('komponenta_obdobi', {}).get('value', "")
                                ]
                                feat.setAttributes(atributy)
                                feats_k.append(feat)

        if not target_pian_ids:
            iface.messageBar().pushMessage("AMCR", f"Nalezeno {len(docs)} záznamů, ale žádný nemá geometrii.", level=1)
            return        


        # ==========================================
        # B) Geometry (PIAN)
        # ==========================================
        ids_list = list(target_pian_ids)
        total_pians = len(ids_list)
        docs_pian = []
        BATCH_PIAN = 50 
        
        iface.messageBar().pushMessage("AMCR", f"Záznamů: {len(docs)} (z toho {actions_with_geom} s mapou). Stahuji {total_pians} unikátních geometrií, vykresluji {target_pian_ids_count} geometrií...", level=1)
        
        # Seznam polí pro PIAN
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
        # C) TVORBA VRSTEV
        # ==========================================
        
        
        if typ_dat == "akce":
            archeologicky_zaznam = "Akce"
        elif typ_dat == "lokalita":
            archeologicky_zaznam = "Lokalita"

        vl_poly = QgsVectorLayer("Polygon?crs=epsg:5514", f"AMCR_{archeologicky_zaznam}_Polygony", "memory")
        vl_line = QgsVectorLayer("LineString?crs=epsg:5514", f"AMCR_{archeologicky_zaznam}_Linie", "memory")
        vl_point = QgsVectorLayer("Point?crs=epsg:5514", f"AMCR_{archeologicky_zaznam}_Body", "memory")
        layers = [vl_poly, vl_line, vl_point]

        # Definice sloupců atributové tabulky
        cols = [
            QgsField("PIAN", QVariant.String),
            QgsField("Přesnost", QVariant.String),
            QgsField("PIAN – typ", QVariant.String),
            QgsField("Dokumentační jednotka", QVariant.String),
            QgsField("Typ dokumentační jednotky", QVariant.String),
            QgsField("Definiční bod(y) (WGS-84)", QVariant.String),
            QgsField(archeologicky_zaznam, QVariant.String),
            QgsField("Odkaz do Digitálního archivu AMČR", QVariant.String),
            QgsField("Okres", QVariant.String),
            QgsField("Katastr", QVariant.String),
            QgsField("Další katastry", QVariant.String)
        ]

        if typ_dat == "akce":
            cols += [
                QgsField("Akce – lokalizace", QVariant.String),
                QgsField("Vedoucí akce", QVariant.String),
                QgsField("Organizace", QVariant.String),
                QgsField("Specifikace data", QVariant.String),
                QgsField("Datum zahájeni", QVariant.String),
                QgsField("Datum ukončení", QVariant.String),
                QgsField("Hlavní typ", QVariant.String),
                QgsField("Vedlejší typ", QVariant.String),
                QgsField("Zjištění", QVariant.String),                
                QgsField("Akce – nahrazuje NZ", QVariant.String),
            ]
        elif typ_dat == "lokalita":
            cols += [
                QgsField("nazev_lokality", QVariant.String),
                QgsField("popis_lokality", QVariant.String),
                QgsField("typ_lokality", QVariant.String),
                QgsField("druh_lokality", QVariant.String),
                QgsField("zachovalost", QVariant.String)
            ]
        
        cols.append(QgsField("Přístupnost", QVariant.String))

        alias_map = { # aliasy i pro ostatní pole ve v2.0.0
            "nazev_lokality": "Název lokality",
            "popis_lokality": "Popis lokality",
            "typ_lokality": "Typ lokality",
            "druh_lokality": "Druh lokality",
            "zachovalost": "Zachovalost"
        }        

        if komponenty == "true":
            vl_komponenty = QgsVectorLayer("None", "AMCR Komponenty", "memory")
            pr = vl_komponenty.dataProvider()
            komponenty_cols = [
                QgsField("komponenta", QVariant.String), # ident_cely
                QgsField("dj_id", QVariant.String),
                # potenciálně QgsField("komponenta_aktivita", QVariant.String),
                QgsField("komponenta_areal", QVariant.String),
                QgsField("komponenta_obdobi", QVariant.String)
            ]
            pr.addAttributes(komponenty_cols)
            vl_komponenty.updateFields()

            idx_dj_id = vl_komponenty.fields().indexOf("dj_id")
            text_setup = QgsEditorWidgetSetup("TextEdit", {})
            vl_komponenty.setEditorWidgetSetup(idx_dj_id, text_setup)

        for vl in layers:
            vl.dataProvider().addAttributes(cols)
            vl.updateFields()
            for tech_name, alias in alias_map.items():
                idx = vl.fields().lookupField(tech_name)
                if idx != -1:
                    vl.setFieldAlias(idx, alias)
            
        feats_p, feats_l, feats_pt = [], [], []
        
        for doc in docs_pian:
            try:
                pid = doc.get('ident_cely', '')
                if pid not in pian_lookup:
                    continue 
                                
                metas = pian_lookup[pid]
                
                # Geometry processing
                raw = doc.get('pian_chranene_udaje')
                if isinstance(raw, list) and raw:
                    raw = raw[0]
                jdata = json.loads(raw) if isinstance(raw, str) else (raw if isinstance(raw, dict) else {})
                
                wkt = None
                if jdata.get('geom_sjtsk_wkt'):
                    wkt = jdata['geom_sjtsk_wkt'].get('value')
                elif jdata.get('geom_wkt'):
                    wkt = jdata['geom_wkt'].get('value')
                
                # PIAN attributes
                pian_presnost = tr_code(str(doc.get('pian_presnost', '')))
                pian_typ = tr_code(str(doc.get('pian_typ', '')))

                if filters and filters.get('f_pian_presnost') and doc.get('pian_presnost') not in filters.get('f_pian_presnost'):
                    continue

                if wkt:
                    geom = QgsGeometry.fromWkt(wkt)
                    if geom.isGeosValid():

                        for meta in metas:
                            feat = QgsFeature()
                            feat.setGeometry(geom)
                            atributy = [
                                pid, 
                                pian_presnost,
                                pian_typ,
                                meta['dj_id'],
                                meta['dj_typ_value'],
                                meta['loc'],
                                meta['ident_cely'],
                                "https://digiarchiv.aiscr.cz/id/" + meta['ident_cely'],
                                meta['az_okres'],
                                meta['katastr'],
                                meta['dalsi_katastr']
                            ]
                            if typ_dat == "akce":
                                atributy += [
                                    meta['lokalizace_okolnosti'],
                                    meta['akce_hlavni_vedouci'],
                                    meta['akce_organizace'],
                                    meta['akce_specifikace_data'],
                                    meta['akce_datum_zahajeni'],
                                    meta['akce_datum_ukonceni'],
                                    meta['akce_hlavni_typ'],
                                    meta['akce_vedlejsi_typ'],
                                    meta['dj_negativni'],                                    
                                    meta['akce_je_nz']
                                ]

                            elif typ_dat == "lokalita":
                                atributy += [
                                    meta['lokalita_nazev'],
                                    meta['lokalita_popis'],
                                    meta['lokalita_typ'],
                                    meta['lokalita_druh'],
                                    meta['lokalita_zachovalost']
                                ]

                            atributy.append(meta['pristupnost'])

                            feat.setAttributes(atributy)

                            t = geom.type()
                            if t == QgsWkbTypes.PolygonGeometry:
                                feats_p.append(feat)
                            elif t == QgsWkbTypes.LineGeometry:
                                feats_l.append(feat)
                            elif t == QgsWkbTypes.PointGeometry:
                                feats_pt.append(feat)
            except Exception as ex:
                print(f"Chyba při tvorbě feature: {ex}")
                pass

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
            iface.messageBar().pushMessage("AMCR", f"Hotovo. Záznamů: {len(docs)} (s geom: {actions_with_geom}). Vykresleno: {added} prvků.", level=0)

            # Relation 
            if komponenty == "true":
                parent_layers = [
                    (vl_poly, "Polygony"),
                    (vl_line, "Linie"),
                    (vl_point, "Body")
                ]
                rel_manager = proj.relationManager()
                for parent_layer, label in parent_layers:
                    rel = QgsRelation()
                    #rel_id = f"rel_{parent_layer.id()}_komponenty"
                    rel_name = f"Komponenty pro {label}"
                    #rel.setId(rel_id)                    
                    rel.setName(rel_name)                    
                    rel.setReferencingLayer(vl_komponenty.id())
                    rel.setReferencedLayer(parent_layer.id())
                    rel.addFieldPair("dj_id", "Dokumentační jednotka") # Upravit název parent sloupce po změně názvů sloupců u vrstev akcí/lokalit
                    rel.generateId()
                    if rel.isValid():
                        rel_manager.addRelation(rel)
                    else:
                        print(f"Relace pro {label} není validní!")

        else:
            iface.messageBar().pushMessage("AMCR", "Žádná data k zobrazení.", level=1)

    except Exception as e:
        iface.messageBar().pushMessage("Chyba", str(e), level=2)
    finally:
        QApplication.restoreOverrideCursor()
