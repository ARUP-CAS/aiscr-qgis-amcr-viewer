# -*- coding: utf-8 -*-
from qgis.core import (QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry,
                       QgsField, QgsCoordinateReferenceSystem,
                       QgsCoordinateTransform, QgsWkbTypes, Qgis,
                       QgsMessageLog)
from qgis.utils import iface
from qgis.PyQt.QtCore import Qt, QMetaType
from qgis.PyQt.QtWidgets import QApplication
from qgis.PyQt.QtGui import QCursor
import requests
import json

# Global cache to store translated terms from the Digital Archive
TRANSLATIONS = {}

# Session with authentication cookie after login;
# None = not logged in (anonymous access)
AMCR_SESSION: requests.Session | None = None

# Re-entrancy guard: the download runs in the main thread and pumps the
# event loop via processEvents(), so the user could otherwise start
# a second download while the first one is still running
_LOADING = False


def _log(msg: str, level=Qgis.MessageLevel.Info):
    """
    Shortcut: writes a message to the QGIS log
    (Messages panel → AMČR tab).
    """
    QgsMessageLog.logMessage(msg, "AMČR login", level)


def login_to_api(username: str, password: str):
    """
    Logs in to the Digiarchiv API using a username and password.
    Returns a requests.Session with the session cookie set, or None on error.
    """
    login_url = "https://digiarchiv.aiscr.cz/api/user/login"

    _log(f"Přihlašuji uživatele: '{username}'")

    if not username or not password:
        _log(
            "CHYBA: username nebo heslo je prázdné.",
            Qgis.MessageLevel.Critical
        )
        return None

    session = requests.Session()
    session.headers.update({
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "User-Agent": "QGIS-Plugin/1.0 (AISCR Data Fetcher)"
    })

    try:
        _log(f"Odesílám POST na {login_url} ...")
        response = session.post(
            login_url,
            json={"user": username, "pwd": password},
            timeout=10
        )
        _log(f"HTTP status: {response.status_code}")
        response.raise_for_status()

        # The API returns errors with status code 200 –
        # the response body must be checked
        body = response.json()
        if "error" in body:
            _log(
                f"CHYBA přihlášení (API): {body['error']}",
                Qgis.MessageLevel.Critical
            )
            return None

        _log("Přihlášení proběhlo úspěšně.")
        global AMCR_SESSION
        AMCR_SESSION = session
        return session

    except requests.exceptions.HTTPError as e:
        _log(f"CHYBA HTTP {e.response.status_code if e.response else '?'}: "
             f"{e.response.text[:300] if e.response else 'žádná odpověď'}",
             Qgis.MessageLevel.Critical)
        return None
    except requests.exceptions.RequestException as e:
        _log(f"CHYBA sítě: {e}", Qgis.MessageLevel.Critical)
        return None
    except ValueError:
        # Server returned non-JSON (e.g. an HTML error page behind a proxy)
        _log("CHYBA: server nevrátil platný JSON: "
             f"{response.text[:300]}",
             Qgis.MessageLevel.Critical)
        return None


def _get_session() -> requests.Session | None:
    """
    Returns the active session. If none exists (e.g. after a QGIS restart),
    attempts automatic login using stored credentials.
    Returns None if no credentials are stored.
    """
    global AMCR_SESSION
    if AMCR_SESSION is not None:
        return AMCR_SESSION

    # Attempt auto-login using stored credentials
    from .amcr_dialog import LoginDialog
    username, password = LoginDialog.get_credentials()
    if username and password:
        _log("Session vypršela nebo chybí – automatické přihlášení...")
        AMCR_SESSION = login_to_api(username, password)

    return AMCR_SESSION


def _api_get_json(url, params, timeout=30) -> dict:
    """
    Performs a GET request and returns the parsed JSON body.
    If the API signals an expired login, re-authenticates once and retries.
    The body is parsed exactly once (the auth check reuses it).
    Raises ValueError if the server does not return valid JSON.
    """
    global AMCR_SESSION

    def _is_auth_error(resp: requests.Response, body) -> bool:
        """The API returns auth errors with status 200 –
        the body must be checked."""
        if resp.status_code == 401:
            return True
        if not isinstance(body, dict):
            return False
        err = str(body.get("error", "")).lower()
        return (
            "unauthorized" in err
            or "not logged" in err
            or "session" in err
        )

    def _parse(resp):
        try:
            return resp.json()
        except ValueError:
            return None

    session = _get_session()
    resp = (session or requests).get(url, params=params, timeout=timeout)
    body = _parse(resp)

    if _is_auth_error(resp, body):
        _log("Session vypršela během stahování – obnovuji přihlášení...",
             Qgis.MessageLevel.Warning)
        AMCR_SESSION = None  # Invalidate the old session
        from .amcr_dialog import LoginDialog
        username, password = LoginDialog.get_credentials()
        if username and password:
            AMCR_SESSION = login_to_api(username, password)
            if AMCR_SESSION:
                resp = AMCR_SESSION.get(url, params=params, timeout=timeout)
                body = _parse(resp)
            else:
                _log("Opakované přihlášení selhalo.",
                     Qgis.MessageLevel.Critical)
        else:
            _log("Přihlašovací údaje nejsou uloženy – pokračuji anonymně.",
                 Qgis.MessageLevel.Warning)

    if body is None:
        raise ValueError(
            f"API nevrátilo platný JSON (HTTP {resp.status_code})"
        )
    return body


def load_translations():
    """
    Fetches the official Czech translation dictionary
    from the Digiarchive API.
    """
    global TRANSLATIONS
    if TRANSLATIONS:
        return

    url = "https://digiarchiv.aiscr.cz/api/assets/i18n/cs.json"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            TRANSLATIONS = r.json()
    except Exception as e:
        QgsMessageLog.logMessage(
            f"Error downloading vocabulary: {e}",
            "AMČR", Qgis.MessageLevel.Warning
        )


def tr_code(code):
    """
    Translates a technical code into a human-readable string
    using the global cache.
    """
    if not code:
        return ""
    return TRANSLATIONS.get(code, code)


def komp_projde_filtrem(komp, filter_areal, filter_datace, filters):
    # 'or {}' – the key may be present with a None value
    areal_id = (komp.get('komponenta_areal') or {}).get('id', "")
    if filter_areal and areal_id not in filters.get('f_areal', []):
        return False

    obdobi_id = (komp.get('komponenta_obdobi') or {}).get('id', "")
    if filter_datace and obdobi_id not in filters.get('f_obdobi', []):
        return False

    return True


def load_amcr_data(canvas, bb, filters=None,
                   typ_dat="akce", komponenty="false"):
    """
    Main processing function:
    1. Determines search area (Bounding Box)
    2. Fetches metadata and geometries from API
    3. Creates QGIS memory layers and populates them with features
    """
    global _LOADING
    if _LOADING:
        iface.messageBar().pushMessage(
            "AMCR",
            "Stahování již probíhá, počkejte na jeho dokončení.",
            level=Qgis.MessageLevel.Warning
        )
        return
    _LOADING = True

    load_translations()

    # --- 1. COORDINATE TRANSFORMATION ---
    # Get current map extent and transform it
    # from project CRS (usually S-JTSK) to WGS-84 for the API
    extent = canvas.extent()
    crs_src = canvas.mapSettings().destinationCrs()
    crs_dest = QgsCoordinateReferenceSystem("EPSG:4326")
    xform = QgsCoordinateTransform(crs_src, crs_dest, QgsProject.instance())
    extent_wgs = xform.transformBoundingBox(extent)

    # Format the bounding box string as required by the API:
    # minLat,minLon,maxLat,maxLon
    bbox_str = (
        f"{extent_wgs.yMinimum()},{extent_wgs.xMinimum()},"
        f"{extent_wgs.yMaximum()},{extent_wgs.xMaximum()}"
    )

    url = "https://digiarchiv.aiscr.cz/api/search/query"

    iface.messageBar().pushMessage(
        "AMCR",
        "Hledám záznamy...",
        level=Qgis.MessageLevel.Info
    )
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

        # Apply multi-select filters from the dialog using
        # the ':or' syntax required by the API
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

        seen_ids = set()
        fetched_total = 0  # All downloaded records incl. duplicates
        target_pian_ids_count = 0

        # Check if we should skip negative results based on filter
        skip_negativni = (
            filters.get('posevidence') == 'true'
            if filters
            else False
        )

        # Check whether we should filter results based on component filters
        filter_areal = "f_areal" in filters if filters else False
        filter_datace = "f_obdobi" in filters if filters else False

        # Set when a network error interrupts the download – the user
        # gets an explicit error/warning instead of a silent partial result
        network_error = False

        # --- API PAGINATION LOOP ---
        while True:
            base_params['rows'] = BATCH_DOCS
            if current_page > 0:
                base_params['page'] = current_page
            elif 'page' in base_params:
                del base_params['page']

            try:
                resp_json = _api_get_json(url, params=base_params, timeout=30)
                data = resp_json.get('response', {})
                batch_docs = data.get('docs', [])
                num_found = data.get('numFound', 0)

                if not batch_docs:
                    break

                fetched_total += len(batch_docs)

                # Filter out duplicates and append to main list
                new_docs = []
                for d in batch_docs:
                    ident = d.get('ident_cely')
                    if ident and ident not in seen_ids:
                        seen_ids.add(ident)
                        new_docs.append(d)

                docs.extend(new_docs)
                QgsMessageLog.logMessage(
                    f"Strana {current_page} stažena. "
                    f"Celkem záznamů: {len(docs)} / {num_found}",
                    "AMČR", Qgis.MessageLevel.Info
                )

                # Compare downloaded (not unique) records against numFound –
                # pages full of duplicates would otherwise trigger
                # needless extra requests
                if fetched_total >= num_found:
                    break
                if len(docs) >= MAX_LIMIT:
                    iface.messageBar().pushMessage(
                        "AMCR",
                        f"Limit {MAX_LIMIT} záznamů dosažen.",
                        level=Qgis.MessageLevel.Warning
                    )
                    break

                current_page += 1
                QApplication.processEvents()  # Keep UI responsive

            except requests.exceptions.RequestException as e:
                network_error = True
                QgsMessageLog.logMessage(
                    f"Chyba sítě při stránkování na straně "
                    f"{current_page}: {e}",
                    "AMČR", Qgis.MessageLevel.Critical
                )
                break
            except Exception as e:
                QgsMessageLog.logMessage(
                    f"Chyba při stránkování na straně {current_page}: {e}",
                    "AMČR", Qgis.MessageLevel.Warning
                )
                break

        if network_error and not docs:
            iface.messageBar().pushMessage(
                "AMCR",
                "Stahování selhalo: chyba sítě. "
                "Zkontrolujte připojení k internetu.",
                level=Qgis.MessageLevel.Critical
            )
            return

        if not docs:
            iface.messageBar().pushMessage(
                "AMCR",
                "Žádné záznamy nenalezeny.",
                level=Qgis.MessageLevel.Warning
            )
            return

        # ==========================================
        # B) ATTRIBUTE PARSING
        # ==========================================

        # pian_lookup maps a Geometry ID (PIAN)
        # to a list of its associated metadata
        pian_lookup = {}
        target_pian_ids = set()
        actions_with_geom = 0

        # Helper: safely extract a single value
        def g(doc, key, default=""):
            val = doc.get(key)
            if isinstance(val, list):
                return str(val[0]) if val else default
            return str(val) if val is not None else default

        # Helper: safely extract and join a list of values
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

            # Extract protected fields ('or {}' – key may hold None)
            az_chranene = doc.get('az_chranene_udaje') or {}
            chranene = (
                doc.get('akce_chranene_udaje')
                or doc.get('lokalita_chranene_udaje')
                or {}
            )

            # Format additional cadastral areas from nested dicts
            dalsi_kat = az_chranene.get('dalsi_katastr', [])
            dalsi_kat_str = ""
            if isinstance(dalsi_kat, list):
                items = [
                    x.get('value', '') if isinstance(x, dict) else str(x)
                    for x in dalsi_kat
                ]
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
                    "akce_hlavni_vedouci": g(
                        doc,
                        'akce_hlavni_vedouci'
                    ),
                    "akce_organizace": tr_code(g(
                        doc,
                        'akce_organizace'
                    )),
                    "akce_specifikace_data": tr_code(g(
                        doc,
                        'akce_specifikace_data'
                    )),
                    "akce_datum_zahajeni": g(
                        doc,
                        'akce_datum_zahajeni'
                    ),
                    "akce_datum_ukonceni": g(
                        doc,
                        'akce_datum_ukonceni'
                    ),
                    "akce_hlavni_typ": tr_code(g(
                        doc,
                        'akce_hlavni_typ'
                    )),
                    "akce_vedlejsi_typ": g_list(
                        doc,
                        'akce_vedlejsi_typ',
                        translate=True
                    ),
                    "lokalizace_okolnosti": (
                        str(lokalizace)
                        if lokalizace
                        else ""
                    ),
                    "akce_je_nz": (
                        "Ano"
                        if doc.get('akce_je_nz') is True
                        else "Ne"
                    ),
                })

            elif typ_dat == "lokalita":
                meta.update({
                    "lokalita_nazev": lokalita_nazev,
                    "lokalita_popis": lokalita_popis,
                    "lokalita_zachovalost": tr_code(g(
                        doc,
                        'lokalita_zachovalost'
                    )),
                    "lokalita_druh": tr_code(g(
                        doc,
                        'lokalita_druh'
                    )),
                    "lokalita_typ": tr_code(g(
                        doc,
                        'lokalita_typ_lokality'
                    )),
                })

            # Documentation units (DJ) within the record
            djs = doc.get('az_dokumentacni_jednotka', [])

            for dj in djs:
                # Skip negative evidence units if requested
                if skip_negativni and dj.get('dj_negativni_jednotka') is True:
                    continue

                komps = dj.get('dj_komponenta', [])

                if filter_areal or filter_datace:
                    if not komps:
                        continue
                    if not any(
                        komp_projde_filtrem(
                            komp, filter_areal,
                            filter_datace, filters
                        )
                        for komp in komps
                    ):
                        continue

                dj_id = dj.get('ident_cely')
                dj_typ = dj.get('dj_typ')

                # Merge shared metadata with documentation unit-specific fields
                dj_meta = {
                    **meta,
                    'dj_id': dj_id,
                    'dj_typ_value': dj_typ.get('value') if dj_typ else "",
                    'dj_negativni': (
                        "Negativní"
                        if dj.get('dj_negativni_jednotka') is True
                        else "Pozitivní"
                    )
                }

                # Link Documentation Unit to Geometry (PIAN)
                dj_pian = dj.get('dj_pian')
                if dj_pian:
                    dj_pian_value = dj_pian.get('id')
                    if dj_pian_value:
                        target_pian_ids.add(dj_pian_value)
                        if dj_pian_value not in pian_lookup:
                            pian_lookup[dj_pian_value] = []

                        if komponenty == "true":
                            # One feature per component –
                            # all data on a single row, no relations needed
                            if komps:
                                for komp in komps:
                                    if not komp_projde_filtrem(
                                        komp, filter_areal,
                                        filter_datace, filters
                                    ):
                                        continue

                                    komp_meta = {
                                        **dj_meta,
                                        'komponenta_id': komp.get(
                                            'ident_cely',
                                            ""
                                            ),
                                        'komponenta_areal': (
                                            komp.get('komponenta_areal')
                                            or {}
                                        ).get('value', ""),
                                        'komponenta_obdobi': (
                                            komp.get('komponenta_obdobi')
                                            or {}
                                        ).get('value', ""),
                                    }
                                    pian_lookup[dj_pian_value].append(komp_meta)
                                    target_pian_ids_count += 1
                            else:
                                # DJ without components — still include
                                # with empty component fields
                                if filter_areal or filter_datace:
                                    continue

                                empty_meta = {
                                    **dj_meta,
                                    'komponenta_id': "",
                                    'komponenta_areal': "",
                                    'komponenta_obdobi': "",
                                }
                                pian_lookup[dj_pian_value].append(empty_meta)
                                target_pian_ids_count += 1
                        else:
                            target_pian_ids_count += 1
                            pian_lookup[dj_pian_value].append(dj_meta)

        if not target_pian_ids:
            iface.messageBar().pushMessage(
                "AMCR",
                f"Nalezeno {len(docs)} záznamů, ale žádný nemá geometrii.",
                level=Qgis.MessageLevel.Warning
            )
            return

        # ==========================================
        # C) GEOMETRY FETCHING (PIAN)
        # ==========================================
        ids_list = list(target_pian_ids)
        total_pians = len(ids_list)
        docs_pian = []
        # Geometry requests are batch-processed
        # to stay under URL length limits:
        BATCH_PIAN = 200

        iface.messageBar().pushMessage(
            "AMCR",
            f"Záznamů: {len(docs)} (z toho {actions_with_geom} s mapou). "
            f"Stahuji {total_pians} unikátních geometrií, "
            f"vykresluji {target_pian_ids_count} geometrií...",
            level=Qgis.MessageLevel.Info
        )

        fl_pian = [
            "ident_cely", "pian_typ",
            "pian_chranene_udaje", "pian_presnost"
        ]

        for i in range(0, total_pians, BATCH_PIAN):
            batch = ids_list[i: i + BATCH_PIAN]
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
                r_json = _api_get_json(url, params=params_pian, timeout=15)
                docs_pian.extend(r_json.get('response', {}).get('docs', []))
            except requests.exceptions.RequestException as e:
                # Network is down – stop immediately instead of
                # uselessly retrying every remaining batch
                network_error = True
                QgsMessageLog.logMessage(
                    f"Chyba sítě při stahování geometrií PIAN: {e}",
                    "AMČR", Qgis.MessageLevel.Critical
                )
                break
            except Exception as e:
                QgsMessageLog.logMessage(
                    f"Chyba PIAN: {e}",
                    "AMČR", Qgis.MessageLevel.Warning
                )

        # ==========================================
        # D) LAYER CREATION (QGIS Memory Layers)
        # ==========================================

        archeologicky_zaznam = "Akce" if typ_dat == "akce" else "Lokalita"

        # Initialize three layers for different geometry types (S-JTSK CRS)
        vl_poly = QgsVectorLayer(
            "Polygon?crs=epsg:5514",
            f"AMCR_{archeologicky_zaznam}_Polygony",
            "memory"
        )
        vl_line = QgsVectorLayer(
            "LineString?crs=epsg:5514",
            f"AMCR_{archeologicky_zaznam}_Linie",
            "memory"
        )
        vl_point = QgsVectorLayer(
            "Point?crs=epsg:5514",
            f"AMCR_{archeologicky_zaznam}_Body",
            "memory"
        )
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
            "zachovalost": "Zachovalost",
            "komponenta": "Komponenta",
            "komponenta_areal": "Areál",
            "komponenta_obdobi": "Období",
        }

        if komponenty == "true":
            cols += [
                QgsField("komponenta", QMetaType.Type.QString),
                QgsField("komponenta_areal", QMetaType.Type.QString),
                QgsField("komponenta_obdobi", QMetaType.Type.QString),
            ]

        for vl in layers:
            vl.dataProvider().addAttributes(cols)
            vl.updateFields()
            for tech_name, alias in alias_map.items():
                idx = vl.fields().lookupField(tech_name)
                if idx != -1:
                    vl.setFieldAlias(idx, alias)

        # Lists to hold features before batch-adding to layers
        feats_p, feats_l, feats_pt = [], [], []

        # Transform for PIANs that only provide WGS-84 geometry (geom_wkt) –
        # the target layers are in S-JTSK (EPSG:5514)
        xform_wgs_to_sjtsk = QgsCoordinateTransform(
            QgsCoordinateReferenceSystem("EPSG:4326"),
            QgsCoordinateReferenceSystem("EPSG:5514"),
            QgsProject.instance()
        )

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
                jdata = (
                    json.loads(raw)
                    if isinstance(raw, str)
                    else (raw or {})
                )

                wkt = None
                wkt_is_wgs = False
                if jdata.get('geom_sjtsk_wkt'):
                    wkt = jdata.get('geom_sjtsk_wkt', {}).get('value')
                elif jdata.get('geom_wkt'):
                    # Fallback geometry is in WGS-84 and must be
                    # transformed to S-JTSK before use
                    wkt = jdata.get('geom_wkt', {}).get('value')
                    wkt_is_wgs = True

                # The API may return the value as a single-item list –
                # normalize before comparing against filter codes
                raw_presnost = doc.get('pian_presnost', '')
                if isinstance(raw_presnost, list):
                    raw_presnost = raw_presnost[0] if raw_presnost else ''
                raw_typ = doc.get('pian_typ', '')
                if isinstance(raw_typ, list):
                    raw_typ = raw_typ[0] if raw_typ else ''

                pian_presnost = tr_code(str(raw_presnost))
                pian_typ = tr_code(str(raw_typ))

                # Final precision filter check
                if (
                    filters
                    and filters.get('f_pian_presnost')
                    and str(raw_presnost)
                    not in filters.get('f_pian_presnost')
                ):
                    continue

                if wkt:
                    geom = QgsGeometry.fromWkt(wkt)
                    if geom.isNull():
                        continue
                    if wkt_is_wgs:
                        geom.transform(xform_wgs_to_sjtsk)
                    if not geom.isGeosValid():
                        # Try to repair (e.g. self-intersections)
                        # instead of silently dropping the feature
                        geom = geom.makeValid()
                    if geom.isGeosValid():
                        t = geom.type()
                        target_list = None
                        if t == QgsWkbTypes.PolygonGeometry:
                            target_list = feats_p
                        elif t == QgsWkbTypes.LineGeometry:
                            target_list = feats_l
                        elif t == QgsWkbTypes.PointGeometry:
                            target_list = feats_pt

                        if target_list is None:
                            continue

                        is_akce = (typ_dat == "akce")

                        # Create a QGIS feature for each documentation unit
                        # associated with this geometry
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
                                "https://digiarchiv.aiscr.cz/id/"
                                + meta['ident_cely'],
                                meta['az_okres'],
                                meta['katastr'],
                                meta['dalsi_katastr']
                            ]
                            if is_akce:
                                atributy.extend([
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
                                ])
                            else:
                                atributy.extend([
                                    meta['lokalita_nazev'],
                                    meta['lokalita_popis'],
                                    meta['lokalita_typ'],
                                    meta['lokalita_druh'],
                                    meta['lokalita_zachovalost']
                                ])

                            atributy.append(meta['pristupnost'])

                            if komponenty == "true":
                                atributy.extend([
                                    meta.get('komponenta_id', ""),
                                    meta.get('komponenta_areal', ""),
                                    meta.get('komponenta_obdobi', ""),
                                ])

                            feat.setAttributes(atributy)
                            target_list.append(feat)

            except Exception as ex:
                QgsMessageLog.logMessage(
                    f"Chyba při tvorbě feature: {ex}",
                    "AMČR", Qgis.MessageLevel.Warning
                )

# --- ADDING TO QGIS INTERFACE ---
        proj = QgsProject.instance()
        added = 0
        layers_to_process = [
            (feats_p, vl_poly, "Polygony"),
            (feats_l, vl_line, "Linie"),
            (feats_pt, vl_point, "Body"),
        ]

        for f, l, n in layers_to_process:
            if f:
                l.dataProvider().addFeatures(f)
                l.updateExtents()
                l.setName(f"AMCR_{archeologicky_zaznam}_{n}")
                proj.addMapLayer(l)
                added += len(f)

        if network_error:
            iface.messageBar().pushMessage(
                "AMCR",
                "Stahování bylo přerušeno chybou sítě – "
                f"výsledek je neúplný (vykresleno {added} prvků). "
                "Zkontrolujte připojení a spusťte stahování znovu.",
                level=(
                    Qgis.MessageLevel.Warning
                    if added > 0
                    else Qgis.MessageLevel.Critical
                )
            )
        elif added > 0:
            iface.messageBar().pushMessage(
                "AMCR",
                f"Hotovo. Záznamů: {len(docs)} (s geom: {actions_with_geom}). "
                f"Vykresleno: {added} prvků.",
                level=Qgis.MessageLevel.Success
            )
        else:
            iface.messageBar().pushMessage(
                "AMCR",
                "Žádná data k zobrazení.",
                level=Qgis.MessageLevel.Info
            )

    except Exception as e:
        iface.messageBar().pushMessage(
            "Chyba",
            str(e),
            level=Qgis.MessageLevel.Critical
        )
    finally:
        # Always restore cursor and release the guard, even after failure
        _LOADING = False
        QApplication.restoreOverrideCursor()
