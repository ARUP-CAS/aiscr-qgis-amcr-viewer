# -*- coding: utf-8 -*-
from qgis.gui import QgsMapToolIdentifyFeature
from qgis.core import (QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry, 
                       QgsField, QgsCoordinateReferenceSystem, QgsCoordinateTransform,
                       QgsWkbTypes)
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
    if TRANSLATIONS: return 
    
    url = "https://digiarchiv.aiscr.cz/api/assets/i18n/cs.json"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            TRANSLATIONS = r.json()
    except Exception as e:
        print(f"Chyba při stahování hesláře: {e}")

def tr_code(code):
    if not code: return ""
    return TRANSLATIONS.get(code, code)

def load_amcr_data(canvas, bb, filters=None):
    load_translations()

    # 1. Bounding box
    extent = canvas.extent()
    crs_src = canvas.mapSettings().destinationCrs()
    crs_dest = QgsCoordinateReferenceSystem("EPSG:4326")
    xform = QgsCoordinateTransform(crs_src, crs_dest, QgsProject.instance())
    extent_wgs = xform.transformBoundingBox(extent)
    bbox_str = f"{extent_wgs.yMinimum()},{extent_wgs.xMinimum()},{extent_wgs.yMaximum()},{extent_wgs.xMaximum()}"
    
    url = "https://digiarchiv.aiscr.cz/api/search/query"
    
    iface.messageBar().pushMessage("AMCR", "Hledám akce...", level=1)
    QApplication.setOverrideCursor(Qt.WaitCursor)
    
    try:
        # ===================
        # A) METADATA (Fieldwork event)
        # ===================
        
        # Field list
        fl_akce = [
            "ident_cely", "akce_typ", "akce_hlavni_vedouci", "akce_datum_zahajeni", "az_dj_pian", "akce_datum_ukonceni", "loc", "az_okres", 
            "katastr", "az_chranene_udaje", "akce_organizace", "akce_specifikace_data", 
            "akce_hlavni_typ", "akce_vedlejsi_typ", "akce_chranene_udaje", 
            "akce_je_nz", "pristupnost", "dj_negativni_jednotka"
        ]

        base_params = {
            "mapa": "true",
            #"isExport": "true",
            "entity": "akce",
            "sort": "ident_cely asc", 
            "fl": ",".join(fl_akce)
        }

        if bb == "true": 
            base_params["loc_rpt"] = bbox_str

        # Apply filters
        if filters:
            for key, value in filters.items():
                if not value: continue
                if isinstance(value, list):
                    base_params[key] = [f"{v}:or" for v in value]
                else:
                    base_params[key] = str(value).strip()

        docs_akce = []
        current_page = 0 
        BATCH_AKCE = 500
        MAX_LIMIT = 20000 
        
        seen_ids = set()
        
        while True:
            base_params['rows'] = BATCH_AKCE
            if current_page > 0:
                base_params['page'] = current_page
            elif 'page' in base_params:
                del base_params['page']
            
            try:
                resp_akce = requests.get(url, params=base_params, timeout=30)
                resp_json = resp_akce.json()
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
                
                docs_akce.extend(new_docs)
                print(f"Strana {current_page} stažena. Celkem záznamů: {len(docs_akce)} / {num_found}")

                if len(docs_akce) >= num_found:
                    break
                if len(docs_akce) >= MAX_LIMIT:
                    iface.messageBar().pushMessage("AMCR", f"Limit {MAX_LIMIT} záznamů dosažen.", level=1)
                    break
                
                current_page += 1
                QApplication.processEvents()
                
            except Exception as e:
                print(f"Chyba při stránkování na straně {current_page}: {e}")
                break

        if not docs_akce:
             iface.messageBar().pushMessage("AMCR", "Žádné akce nenalezeny.", level=1)
             return

        # ==========================================
        # Attribute parsing
        # ==========================================
        pian_lookup = {}
        target_pian_ids = set()
        actions_with_geom = 0
        
        for akce in docs_akce:
            piani = akce.get('az_dj_pian', [])
            if not piani: continue
            
            negative_pians = set()
            # Pokud je aktivní filtr 'posevidence', projdeme dokumentační jednotky
            if filters and filters.get('posevidence') == 'true':
                djs = akce.get('az_dokumentacni_jednotka', [])
                for dj in djs:
                    # Pokud je jednotka negativní
                    if dj.get('dj_negativni_jednotka') is True:
                        # Získáme ID pianu z objektu (např. {"id": "P-...", "value": "..."})
                        pian_obj = dj.get('dj_pian')
                        if pian_obj and isinstance(pian_obj, dict):
                            negative_pians.add(pian_obj.get('id'))

            actions_with_geom += 1
            
            def g(key, default=""): 
                val = akce.get(key)
                if isinstance(val, list): return str(val[0]) if val else default
                return str(val) if val is not None else default

            def g_list(key, translate=False):
                val = akce.get(key, [])
                if not isinstance(val, list): val = [val] if val else []
                if translate:
                    return ", ".join([tr_code(str(x)) for x in val if x])
                return ", ".join([str(x) for x in val if x])

            az_chranene = akce.get('az_chranene_udaje', {})
            akce_chranene = akce.get('akce_chranene_udaje', {})
            
            dalsi_kat = az_chranene.get('dalsi_katastr', [])
            dalsi_kat_str = ""
            if isinstance(dalsi_kat, list):
                items = [x.get('value', '') if isinstance(x, dict) else str(x) for x in dalsi_kat]
                dalsi_kat_str = ", ".join([i for i in items if i])

            lokalizace = akce_chranene.get('lokalizace_okolnosti', "")

            # Prepate metadata for fieldwork event
            meta = {
                "ident_cely": akce.get('ident_cely', ''),
                "az_okres": g('az_okres'),
                "katastr": g_list('katastr'),
                "dalsi_katastr": dalsi_kat_str,
                "akce_hlavni_vedouci": g('akce_hlavni_vedouci'),
                "akce_organizace": tr_code(g('akce_organizace')),
                "akce_specifikace_data": tr_code(g('akce_specifikace_data')),
                "akce_datum_zahajeni": g('akce_datum_zahajeni'),
                "akce_datum_ukonceni": g('akce_datum_ukonceni'),
                "akce_hlavni_typ": tr_code(g('akce_hlavni_typ')),
                "akce_vedlejsi_typ": g_list('akce_vedlejsi_typ', translate=True),
                "lokalizace_okolnosti": str(lokalizace) if lokalizace else "",
                "akce_je_nz": "Ano" if akce.get('akce_je_nz') is True else "Ne",
                "pristupnost": g('pristupnost'),
                "loc": g_list('loc')
            }
            
            for pid in piani:
                if pid in negative_pians:
                    continue
                pian_lookup[pid] = meta
                target_pian_ids.add(pid)

        if not target_pian_ids:
            iface.messageBar().pushMessage("AMCR", f"Nalezeno {len(docs_akce)} akcí, ale žádná nemá geometrii.", level=1)
            return

        # ==========================================
        # B) Geometry (PIAN)
        # ==========================================
        ids_list = list(target_pian_ids)
        total_pians = len(ids_list)
        docs_pian = []
        BATCH_PIAN = 50 
        
        iface.messageBar().pushMessage("AMCR", f"Akcí: {len(docs_akce)} (z toho {actions_with_geom} s mapou). Stahuji {total_pians} geometrií...", level=1)
        
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
        vl_poly = QgsVectorLayer("Polygon?crs=epsg:5514", "AMCR Plochy", "memory")
        vl_line = QgsVectorLayer("LineString?crs=epsg:5514", "AMCR Linie", "memory")
        vl_point = QgsVectorLayer("Point?crs=epsg:5514", "AMCR Body", "memory")
        layers = [vl_poly, vl_line, vl_point]
        
        # Definice sloupců atributové tabulky
        cols = [
            QgsField("PIAN", QVariant.String),
            QgsField("Přesnost", QVariant.String),
            QgsField("PIAN – typ", QVariant.String),
            QgsField("Definiční bod(y) (WGS-84)", QVariant.String),
            QgsField("Identifikátor", QVariant.String),
            QgsField("Odkaz do Digiarchivu", QVariant.String),
            QgsField("Okres", QVariant.String),
            QgsField("Katastr", QVariant.String),
            QgsField("Další katastry", QVariant.String),
            QgsField("Vedoucí akce", QVariant.String),
            QgsField("Organizace", QVariant.String),
            QgsField("Specifikace data", QVariant.String),
            QgsField("Datum zahájeni", QVariant.String),
            QgsField("Datum ukončení", QVariant.String),
            QgsField("Hlavní typ", QVariant.String),
            QgsField("Vedlejší typ", QVariant.String),
            QgsField("Akce – lokalizace", QVariant.String),
            QgsField("Akce - nahrazuje NZ", QVariant.String),
            QgsField("Přístupnost", QVariant.String)
        ]

        for vl in layers:
            vl.dataProvider().addAttributes(cols)
            vl.updateFields()
            
        feats_p, feats_l, feats_pt = [], [], []
        
        for doc in docs_pian:
            try:
                pid = doc.get('ident_cely', '')
                if pid not in pian_lookup: continue 
                
                meta = pian_lookup[pid]
                
                # Geometry processing
                raw = doc.get('pian_chranene_udaje')
                if isinstance(raw, list) and raw: raw = raw[0]
                jdata = json.loads(raw) if isinstance(raw, str) else (raw if isinstance(raw, dict) else {})
                
                wkt = None
                if jdata.get('geom_sjtsk_wkt'): wkt = jdata['geom_sjtsk_wkt'].get('value')
                elif jdata.get('geom_wkt'): wkt = jdata['geom_wkt'].get('value')
                
                # PIAN attributes
                pian_presnost = tr_code(str(doc.get('pian_presnost', '')))
                pian_typ = tr_code(str(doc.get('pian_typ', '')))

                if wkt:
                    geom = QgsGeometry.fromWkt(wkt)
                    if geom.isGeosValid():
                        feat = QgsFeature()
                        feat.setGeometry(geom)
                        feat.setAttributes([
                            pid, 
                            pian_presnost,
                            pian_typ,
                            meta['loc'],
                            meta['ident_cely'],
                            "https://digiarchiv.aiscr.cz/id/" + meta['ident_cely'],
                            meta['az_okres'],
                            meta['katastr'],
                            meta['dalsi_katastr'],
                            meta['akce_hlavni_vedouci'],
                            meta['akce_organizace'],
                            meta['akce_specifikace_data'],
                            meta['akce_datum_zahajeni'],
                            meta['akce_datum_ukonceni'],
                            meta['akce_hlavni_typ'],
                            meta['akce_vedlejsi_typ'],
                            meta['lokalizace_okolnosti'],
                            meta['akce_je_nz'],
                            meta['pristupnost']
                        ])
                        t = geom.type()
                        if t == QgsWkbTypes.PolygonGeometry: feats_p.append(feat)
                        elif t == QgsWkbTypes.LineGeometry: feats_l.append(feat)
                        elif t == QgsWkbTypes.PointGeometry: feats_pt.append(feat)
            except Exception as ex:
                print(f"Chyba při tvorbě feature: {ex}")
                pass

        proj = QgsProject.instance()
        added = 0
        for f, l, n in [(feats_p, vl_poly, "Plochy"), (feats_l, vl_line, "Linie"), (feats_pt, vl_point, "Body")]:
            if f:
                l.dataProvider().addFeatures(f)
                l.updateExtents()
                l.setName(f"AMČR {n} (Filtrováno)") 
                proj.addMapLayer(l)
                added += len(f)
        
        if added > 0:
            iface.messageBar().pushMessage("AMCR", f"Hotovo. Akcí: {len(docs_akce)} (s geom: {actions_with_geom}). Vykresleno: {added} prvků.", level=0)
        else:
            iface.messageBar().pushMessage("AMCR", "Žádná data k zobrazení.", level=1)

    except Exception as e:
        iface.messageBar().pushMessage("Chyba", str(e), level=2)
    finally:
        QApplication.restoreOverrideCursor()

# class AmcrIdentifyTool(QgsMapToolIdentifyFeature):
#     def __init__(self, canvas):
#         super().__init__(canvas)
#         self.canvas = canvas
#         self.setCursor(Qt.CrossCursor)

#     def canvasReleaseEvent(self, event):
#         results = self.identify(event.x(), event.y(), self.IdentifyMode.TopDownStopAtFirst, self.VectorLayer)
#         if not results: return
#         feature = results[0].mFeature
#         akce_id = None
#         # Změna: hledáme 'ident_cely' (ID akce)
#         idx = feature.fieldNameIndex('ident_cely')
#         if idx != -1:
#             akce_id = feature.attributes()[idx]
        
#         # Fallback na starší názvy polí, kdyby něco
#         if not akce_id:
#              for col in ['akce_id', 'ident_cely', 'pian_id']:
#                 if col in feature.fields().names():
#                     akce_id = feature[col]
#                     break
        
#         if not akce_id: return

#         full_id = akce_id if "api.aiscr.cz" in str(akce_id) else f"https://api.aiscr.cz/id/{akce_id}"
#         url = f"https://api.aiscr.cz/2.2/oai?verb=GetRecord&metadataPrefix=oai_amcr&identifier={full_id}"
        
#         iface.messageBar().pushMessage("AMCR", f"Detail: {akce_id}...", level=1)
#         QApplication.setOverrideCursor(Qt.WaitCursor)
#         try:
#             r = requests.get(url, timeout=5)
#             if r.status_code == 200: self.show_detail(akce_id, r.text)
#         except Exception as e:
#             iface.messageBar().pushMessage("Chyba", str(e), level=2)
#         finally:
#             QApplication.restoreOverrideCursor()

#     def show_detail(self, title, raw_xml):
#         xml = re.sub(r'\sxmlns="[^"]+"', '', raw_xml, count=1)
#         xml = re.sub(r'<(/?)[a-zA-Z0-9]+:', r'<\1', xml)
#         info = ""
#         try:
#             root = ET.fromstring(xml)
#             rec = root.find('.//archeologicky_zaznam')
#             if not rec: info = "Zadna data."
#             else:
#                 kat = rec.find('.//hlavni_katastr')
#                 info += f"<h3>{kat.text if kat is not None else '?'}</h3>"
#                 for dj in rec.findall('.//dokumentacni_jednotka'):
#                     pn = dj.find('pian')
#                     p_txt = pn.text if pn is not None else ""
#                     info += f"<hr><b>PIAN: {p_txt}</b><ul>"
#                     for k in dj.findall('komponenta'):
#                         ob = k.find('obdobi').text or "?"
#                         ar = k.find('areal').text or "?"
#                         info += f"<li>{ob} ({ar})</li>"
#                     info += "</ul>"
#             dlg = QMessageBox()
#             dlg.setWindowTitle(str(title))
#             dlg.setText(info)
#             dlg.setTextFormat(Qt.RichText)
#             dlg.exec_()
#         except: pass