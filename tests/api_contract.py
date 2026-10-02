# -*- coding: utf-8 -*-
"""
API contract test – checks that the live digiarchiv / AMCR OAI API still
answers the way the plugin reads it. Plain requests, no QGIS.

The plugin under test is amcr_viewer/ on this branch; the expectations here
describe what its parsers (amcr_tools.g/g_list, amcr_codelists._facet_name)
actually consume, not the official API documentation.

Status model (per check):
  OK          – the answer matches the recorded expectation
  DRIFT       – the answer differs, but the plugin tolerates the new shape
  FAIL        – the answer differs in a way the plugin does not tolerate
  UNAVAILABLE – network error / timeout / HTTP 5xx after retries

Exit code is 1 when any check is FAIL or DRIFT, 0 otherwise (a run where
everything is UNAVAILABLE is green but visible in the summary).

Outage fast-fail: once a host is unreachable after the full retry cycle,
every later request to that host returns UNAVAILABLE immediately (circuit
breaker, no network I/O) – an all-unreachable run finishes in seconds.

Run (from the repository root, outside the repo use uv --no-project so no
uv.lock appears):

    uv run -q --no-project --with requests==2.34.2 \\
        python tests/api_contract.py

Outputs:
  * stdout: a Markdown table of all checks
  * results-api_contract.json next to the script (cwd) with one entry per
    check: name, status, detail, request URL
  * the same table appended to $GITHUB_STEP_SUMMARY when set

Test area (probe 2026-10-02, anonymous = pristupnost A only):
  TEST_BBOX (Mikulov, south Moravia) 48.8,16.6,48.9,16.75
    akce 185, lokalita 18, samostatny_nalez 2, pian 294
  PAGINATION_BBOX (Praha) 49.9,14.3,50.2,14.7 – akce 20 635 records,
  paginated with rows=100; only akce is paginated here, the other entities
  have few enough records in the small bbox.

Env overrides (for the outage simulation):
  AMCR_DA_URL    base URL of digiarchiv (default
                  https://digiarchiv.aiscr.cz)
  AMCR_OAI_URL   base URL of the AMCR OAI endpoint (default
                  https://api.aiscr.cz/2.2/oai)
  AMCR_TIMEOUT   per-request timeout in seconds (default 30)
"""

import json
import os
import re
import sys
import time
import urllib.parse
import xml.etree.ElementTree as ET  # nosec B405

import requests

JOB = "api_contract"
DA_URL = os.environ.get("AMCR_DA_URL", "https://digiarchiv.aiscr.cz")
OAI_URL = os.environ.get("AMCR_OAI_URL", "https://api.aiscr.cz/2.2/oai")
TIMEOUT = int(os.environ.get("AMCR_TIMEOUT", "30"))

# Small test area chosen by probe (see module docstring). Filter values are
# taken from live facets of this same bbox in the same run, never from the
# bundled codelists.
TEST_BBOX = "48.8,16.6,48.9,16.75"
PAGINATION_BBOX = "49.9,14.3,50.2,14.7"

# Entities the plugin downloads (typ_dat_vocab in amcr_tools.py).
ENTITIES = ["akce", "lokalita", "samostatny_nalez"]

# OAI sets, mirroring amcr_codelists.slovnicek (name -> OAI set).
OAI_SETS = {
    "obdobi": "heslo:obdobi",
    "typ_akce": "heslo:akce_typ",
    "areal": "heslo:areal",
    "kraj": "ruian_kraj",
    "organizace": "organizace",
    "okres": "ruian_okres",
    "katastr": "ruian_katastr",
    "pian_presnost": "heslo:pian_presnost",
    "typ_lokality": "heslo:lokalita_typ",
    "druh_lokality": "heslo:lokalita_druh",
    "jistota": "heslo:jistota_urceni",
    "lokalita_zachovalost": "heslo:stav_dochovani",
    "pristupnost": "heslo:pristupnost",
    "nalez_kategorie": "heslo:predmet_druh_kat",
    "druh_nalezu": "heslo:predmet_druh",
    "specifikace": "heslo:predmet_specifikace",
    "nalezove_okolnosti": "heslo:nalezove_okolnosti",
}

# Facet-backed codelists (name -> (entity, facet field)), mirroring
# amcr_codelists.slovnicek.
FACET_SETS = {
    "vedouci": ("akce", "f_vedouci"),
    "nalezce": ("samostatny_nalez", "f_nalezce"),
}

# Expected facet item shape, as read by amcr_codelists._facet_name:
# list form [str, int] is the current API (Solr 10 / digiarchiv v4.1.0,
# json.nl=arrarr); the object form {"name": str, ...} is the old API
# (pre v4.1.0) which the plugin still tolerates -> DRIFT, not FAIL.
# Any other shape (scalar, empty list item, dict without "name") would
# break the plugin -> FAIL.
FACET_ITEM_FORMS = [
    ("list", lambda x: isinstance(x, list) and len(x) == 2
     and isinstance(x[0], str) and isinstance(x[1], int)),
    ("object", lambda x: isinstance(x, dict)
     and isinstance(x.get("name"), str)),
]

NS = {
    "oai": "http://www.openarchives.org/OAI/2.0/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/",
}

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "amcr-viewer-api-monitor/1.0"})
RESULTS = []
DEPLOYED_VERSION = None

RETRY_BACKOFF = (2, 8)  # seconds, after 1st and 2nd attempt

# Circuit breaker (fast outage): netlocs that came back unreachable after
# the full retry cycle. Every later request to such a host returns None
# immediately, without network I/O – an all-unreachable run then takes
# seconds instead of tens of minutes of per-check retries.
DEAD_HOSTS = set()


def _retry_get(url, params=None):
    """GET with retries on network errors, timeouts and HTTP 5xx.

    Returns the response, or None when unreachable after all attempts.
    HTTP 4xx and error bodies with status 200 are real answers –
    the caller judges them by the contract.

    Once a host (netloc) is found unreachable after full retries, it is
    added to DEAD_HOSTS and every later request to it returns None
    without touching the network (see the module docstring).
    """
    netloc = urllib.parse.urlparse(url).netloc
    if netloc in DEAD_HOSTS:
        return None
    for attempt in range(3):
        try:
            resp = SESSION.get(url, params=params, timeout=TIMEOUT)
            if resp.status_code < 500:
                return resp
        except requests.exceptions.RequestException:
            pass
        if attempt < 2:
            time.sleep(RETRY_BACKOFF[attempt])
    DEAD_HOSTS.add(netloc)
    return None


def record(name, status, detail, url=""):
    RESULTS.append({
        "name": name,
        "status": status,
        "detail": detail,
        "url": url,
    })
    print(f"  {status:<12} {name} – {detail}")


def get_json(url, params=None):
    """GET + JSON parse with a friendly error, or None when unreachable."""
    resp = _retry_get(url, params)
    if resp is None:
        return None
    try:
        return resp.json()
    except ValueError:
        return {"_invalid_json": True, "_status": resp.status_code}


def load_deployed_version():
    """Reads the deployed digiarchiv version from the web bundle.

    Missing version is a DRIFT of its own check, never a FAIL.
    """
    global DEPLOYED_VERSION
    resp = _retry_get(DA_URL + "/home")
    if resp is None:
        record("deployed-version", "UNAVAILABLE",
               f"{DA_URL}/home unreachable")
        return False
    scripts = re.findall(r'(?:src|href)="([^"]*\.js)"', resp.text)
    version = None
    for script in scripts:
        jresp = _retry_get(DA_URL + "/" + script.lstrip("/"))
        if jresp is None:
            continue
        match = re.search(r'raw:"(v\d[^"]*)"', jresp.text)
        if match:
            version = match.group(1)
            break
    if version:
        DEPLOYED_VERSION = version
        record("deployed-version", "OK", f"{version}")
        return True
    record("deployed-version", "DRIFT",
           "git-describe string raw:\"v…\" not found in the web bundle "
           f"({len(scripts)} scripts scanned)")
    return False


def check_translations():
    url = DA_URL + "/api/assets/i18n/cs.json"
    data = get_json(url)
    if data is None:
        record("i18n cs.json", "UNAVAILABLE", "unreachable")
        return
    if not isinstance(data, dict) or not data:
        record("i18n cs.json", "FAIL",
               f"expected a non-empty dict, got {type(data).__name__}",
               url)
        return
    # A few codes the plugin translates via tr_code() in live records
    sample = [k for k in data if k.startswith("HES-")]
    if not sample:
        record("i18n cs.json", "DRIFT",
               "no HES-* keys found – tr_code would return codes verbatim",
               url)
        return
    record("i18n cs.json", "OK",
           f"{len(data)} keys, {len(sample)} HES-* codes", url)


def _status_of_field(types, good, drift=None):
    """OK/DRIFT/FAIL for a set of observed field types."""
    bad = types - good
    if not bad:
        return "OK"
    if drift and bad <= drift:
        return "DRIFT"
    return "FAIL"


def _check_doc_fields(name, docs, fields, url):
    """Checks per-doc field presence and value types the plugin reads.

    fields: {key: (ok_types, drift_types)}
    Value normalization: amcr_tools.g() reads doc.get(key) and str()'s it –
    lists are read as first item. g_list() iterates the value. So both a
    scalar and a list of scalars are consumed; dict values are read with
    .get() by dedicated code paths.
    """
    for key, (good, drift) in fields.items():
        types = set()
        missing = 0
        for doc in docs:
            if key not in doc or doc[key] is None:
                missing += 1
            else:
                v = doc[key]
                if isinstance(v, list):
                    for item in v:
                        types.add(type(item).__name__)
                else:
                    types.add(type(v).__name__)
        if missing == len(docs):
            record(f"{name} {key}", "FAIL",
                   f"missing in all {len(docs)} docs", url)
            continue
        status = _status_of_field(types, good, drift)
        detail = (f"types {sorted(types)}, "
                  f"{missing}/{len(docs)} docs without the key")
        record(f"{name} {key}", status, detail, url)


def fetch_entity_docs(entity, bbox, rows=500):
    """Main query exactly the way the plugin sends it. None = unavailable."""
    params = {
        "mapa": "true",
        "sort": "ident_cely asc",
        "entity": entity,
        "rows": rows,
        "loc_rpt": bbox,
    }
    url = DA_URL + "/api/search/query"
    data = get_json(url, params)
    if data is None:
        return None, None
    if "response" not in data:
        return {}, data
    return data["response"], data


def check_main_queries():
    """Main query per entity: keys and value types the plugin reads."""
    strset = {"str"}
    specs = {
        "akce": {
            "ident_cely": (strset, None),
            "loc": (strset, None),  # g_list -> list of str
            "pristupnost": (strset, None),
            "az_okres": (strset, None),
            "katastr": (strset, None),
            "akce_hlavni_vedouci": (strset, None),
            "akce_organizace": (strset, None),
            "akce_specifikace_data": (strset, None),
            "akce_datum_zahajeni": (strset, None),
            "akce_datum_ukonceni": (strset, None),
            "akce_hlavni_typ": (strset, None),
            "akce_vedlejsi_typ": (strset, None),
            "akce_je_nz": ({"bool"}, None),
            "akce_projekt": (strset, None),
            "az_dj_pian": (strset, None),
            "az_chranene_udaje": ({"dict"}, None),
            "akce_chranene_udaje": ({"dict"}, None),
            "az_dokumentacni_jednotka": ({"dict"}, None),
        },
        "lokalita": {
            "ident_cely": (strset, None),
            "loc": (strset, None),
            "pristupnost": (strset, None),
            "az_okres": (strset, None),
            "katastr": (strset, None),
            "az_dj_pian": (strset, None),
            "az_chranene_udaje": ({"dict"}, None),
            "lokalita_chranene_udaje": ({"dict"}, None),
            "lokalita_druh": (strset, None),
            "lokalita_typ_lokality": (strset, None),
            "lokalita_zachovalost": (strset, None),
            "az_dokumentacni_jednotka": ({"dict"}, None),
        },
        "samostatny_nalez": {
            "ident_cely": (strset, None),
            "loc": (strset, None),
            "pristupnost": (strset, None),
            "samostatny_nalez_nalezce": (strset, None),
            "samostatny_nalez_hloubka": ({"int", "float", "str"}, None),
            "samostatny_nalez_okres": (strset, None),
            "samostatny_nalez_chranene_udaje": ({"dict"}, None),
            "samostatny_nalez_druh_nalezu": (strset, None),
            "samostatny_nalez_obdobi": (strset, None),
            "samostatny_nalez_specifikace": (strset, None),
            "samostatny_nalez_datum_nalezu": (strset, None),
            "samostatny_nalez_pocet": ({"str", "int", "float"}, None),
        },
    }
    docs_by_entity = {}
    for entity in ENTITIES:
        resp, raw = fetch_entity_docs(entity, TEST_BBOX)
        url = DA_URL + "/api/search/query"
        if resp is None:
            record(f"query {entity}", "UNAVAILABLE", "unreachable", url)
            continue
        if "numFound" not in resp and "docs" not in resp:
            record(f"query {entity}", "FAIL",
                   f"no response block: {json.dumps(raw)[:200]}", url)
            continue
        num_found = resp.get("numFound")
        if not isinstance(num_found, int):
            record(f"query {entity} numFound", "FAIL",
                   f"expected int, got {type(num_found).__name__}", url)
            continue
        docs = resp.get("docs", [])
        if not docs:
            record(f"query {entity}", "FAIL",
                   f"0 docs for the test bbox (numFound={num_found}) – "
                   "the test area has no records", url)
            continue
        record(f"query {entity}", "OK",
               f"numFound {num_found}, {len(docs)} docs", url)
        docs_by_entity[entity] = docs
        _check_doc_fields(f"{entity}", docs, specs[entity], url)

    return docs_by_entity


def check_numfound_int():
    url = DA_URL + "/api/search/query"
    for entity in ENTITIES:
        resp, _ = fetch_entity_docs(entity, TEST_BBOX, rows=0)
        if resp is None:
            record(f"numFound {entity}", "UNAVAILABLE", "unreachable", url)
            continue
        if isinstance(resp.get("numFound"), int):
            record(f"numFound {entity}", "OK", f"{resp['numFound']}", url)
        else:
            record(f"numFound {entity}", "FAIL",
                   f"expected int, got {type(resp.get('numFound')).__name__}",
                   url)


def fetch_facets(entity, bbox=None):
    """Facet request exactly the way amcr_codelists.fetch_set sends it."""
    params = {
        "entity": entity,
        "rows": 0,
        "noFacets": "false",
        "onlyFacets": "true",
    }
    if bbox:
        params["loc_rpt"] = bbox
    url = DA_URL + "/api/search/query"
    data = get_json(url, params)
    if data is None:
        return None
    try:
        return data["facet_counts"]["facet_fields"]
    except (KeyError, TypeError):
        return {}


def check_facet_sets():
    """Facet-backed codelists vedouci/nalezce: field exists, item shape."""
    for name, (entity, field) in FACET_SETS.items():
        url = DA_URL + "/api/search/query"
        ff = fetch_facets(entity)
        if ff is None:
            record(f"facet {name}", "UNAVAILABLE", "unreachable", url)
            continue
        if field not in ff:
            record(f"facet {name}", "FAIL",
                   f"facet field {field} missing from entity {entity}", url)
            continue
        items = ff[field]
        if not isinstance(items, list):
            record(f"facet {name}", "FAIL",
                   f"expected a list of items, got {type(items).__name__}",
                   url)
            continue
        if not items:
            record(f"facet {name}", "FAIL",
                   f"facet field {field} came back empty", url)
            continue
        # classify each item's shape
        bad = []
        shapes = set()
        for item in items:
            for shape, test in FACET_ITEM_FORMS:
                if test(item):
                    shapes.add(shape)
                    break
            else:
                bad.append(item)
        if bad:
            record(f"facet {name}", "FAIL",
                   f"{len(bad)}/{len(items)} items in an unknown shape, "
                   f"e.g. {json.dumps(bad[0])[:120]}", url)
        elif shapes == {"list"}:
            record(f"facet {name}", "OK",
                   f"{len(items)} items, shape [value, count]", url)
        elif shapes == {"object"}:
            record(f"facet {name}", "DRIFT",
                   f"{len(items)} items in the OLD object shape "
                   '{"name": …} – the plugin still tolerates it via '
                   "_facet_name, but this is a Solr json.nl change; "
                   "expectation recorded: [value, count]", url)
        else:
            record(f"facet {name}", "DRIFT",
                   f"mixed shapes {sorted(shapes)}", url)


def check_oai_sets():
    """Every OAI set in slovnicek: first page + resumptionToken paging."""
    url = OAI_URL
    for name, oai_set in OAI_SETS.items():
        resp = _retry_get(url, params={
            "verb": "ListRecords",
            "metadataPrefix": "oai_dc",
            "set": oai_set,
        })
        if resp is None:
            record(f"oai {name}", "UNAVAILABLE", "unreachable", url)
            continue
        try:
            root = ET.fromstring(resp.content)  # nosec B405 B314
        except ET.ParseError as e:
            record(f"oai {name}", "FAIL", f"XML parse error: {e}", url)
            continue
        error = root.find(".//oai:error", NS)
        if error is not None:
            record(f"oai {name}", "FAIL",
                   f"OAI error {error.get('code')}: "
                   f"{(error.text or '')[:100]}", url)
            continue
        records = root.findall(".//oai:record", NS)
        if not records:
            record(f"oai {name}", "FAIL",
                   f"set {oai_set} returned no records", url)
            continue
        # record shape: identifier, titles, dc payload
        ok_shape = all(
            r.find(".//oai_dc:dc", NS) is not None
            and r.find(".//dc:identifier", NS) is not None
            for r in records
        )
        if not ok_shape:
            record(f"oai {name}", "FAIL",
                   "record missing oai_dc:dc or dc:identifier", url)
            continue
        token = root.find(".//oai:resumptionToken", NS)
        token_ok = True
        if token is not None and token.text:
            # follow one page of the resumption token, the way fetch_set
            # does; a broken token means an incomplete codelist
            resp2 = _retry_get(url, params={
                "verb": "ListRecords",
                "resumptionToken": token.text,
            })
            if resp2 is None:
                record(f"oai {name}", "UNAVAILABLE",
                       "first page OK, token page unreachable", url)
                continue
            try:
                root2 = ET.fromstring(resp2.content)  # nosec B405 B314
            except ET.ParseError as e:
                record(f"oai {name}", "FAIL",
                       f"token page XML parse error: {e}", url)
                continue
            recs2 = root2.findall(".//oai:record", NS)
            if not recs2:
                token_ok = False
            time.sleep(0.5)  # the plugin pauses between OAI pages
        if token_ok:
            desc = f"{len(records)} records"
            if token is not None and token.text:
                desc += ", token page followed"
            record(f"oai {name}", "OK", desc, url)
        else:
            record(f"oai {name}", "FAIL",
                   "resumptionToken page returned no records", url)


def check_pagination():
    """rows=100 pages over a larger area must not overlap."""
    url = DA_URL + "/api/search/query"
    seen = []
    total = None
    page = 0
    while True:
        params = {
            "mapa": "true",
            "sort": "ident_cely asc",
            "entity": "akce",
            "rows": 100,
            "loc_rpt": PAGINATION_BBOX,
        }
        if page > 0:
            params["page"] = page
        data = get_json(url, params)
        if data is None:
            record("pagination akce", "UNAVAILABLE", "unreachable", url)
            return
        if "response" not in data:
            record("pagination akce", "FAIL",
                   f"error body on page {page}", url)
            return
        resp = data["response"]
        if total is None:
            total = resp.get("numFound")
            if not isinstance(total, int):
                record("pagination akce", "FAIL",
                       "numFound is not an int", url)
                return
        docs = resp.get("docs", [])
        if not docs:
            break
        seen.extend([d.get("ident_cely") for d in docs])
        if len(seen) >= total:
            break
        page += 1
        if page > 220:  # safety stop
            break
    unique = set(seen)
    if len(unique) != len(seen):
        dupes = len(seen) - len(unique)
        record("pagination akce", "FAIL",
               f"{dupes} duplicate ids across {page + 1} pages "
               f"({len(seen)} ids)", url)
    elif len(unique) < total:
        record("pagination akce", "FAIL",
               f"downloaded {len(unique)} of numFound {total}", url)
    else:
        record("pagination akce", "OK",
               f"{len(unique)} unique ids across {page + 1} pages, "
               f"numFound {total}", url)


def check_bbox_restriction():
    """loc_rpt must actually restrict: bbox count << global count."""
    url = DA_URL + "/api/search/query"
    for entity in ENTITIES:
        resp, _ = fetch_entity_docs(entity, TEST_BBOX, rows=0)
        if resp is None:
            record(f"bbox {entity}", "UNAVAILABLE", "unreachable", url)
            continue
        global_resp = get_json(url, params={
            "mapa": "true", "sort": "ident_cely asc", "entity": entity,
            "rows": 0,
        })
        if global_resp is None or "response" not in global_resp:
            record(f"bbox {entity}", "UNAVAILABLE", "global query failed",
                   url)
            continue
        n_bbox = resp.get("numFound")
        n_all = global_resp["response"].get("numFound")
        if not isinstance(n_bbox, int) or not isinstance(n_all, int):
            record(f"bbox {entity}", "FAIL", "numFound not int", url)
            continue
        if n_bbox >= n_all:
            record(f"bbox {entity}", "FAIL",
                   f"loc_rpt did not restrict: {n_bbox} vs {n_all} global",
                   url)
        else:
            record(f"bbox {entity}", "OK",
                   f"{n_bbox} in bbox vs {n_all} global", url)


def check_pian_batch(docs_by_entity):
    """PIAN batch geometry query, exactly the way load_amcr_data sends it."""
    url = DA_URL + "/api/search/query"
    if "akce" not in docs_by_entity:
        record("pian-batch", "UNAVAILABLE",
               "depends on the akce query, which is unavailable", url)
        return
    pian_ids = []
    for doc in docs_by_entity["akce"]:
        for dj in doc.get("az_dokumentacni_jednotka") or []:
            dj_pian = dj.get("dj_pian") or {}
            if dj_pian.get("id"):
                pian_ids.append(dj_pian["id"])
    if not pian_ids:
        record("pian-batch", "FAIL",
               "no dj_pian ids found in the akce docs", url)
        return
    batch = pian_ids[:50]  # small on purpose
    fq = "ident_cely:(" + " OR ".join(batch) + ")"
    data = get_json(url, params={
        "mapa": "true",
        "entity": "pian",
        "q": fq,
        "rows": len(batch),
        "fl": "ident_cely,pian_typ,pian_chranene_udaje,pian_presnost",
    })
    if data is None:
        record("pian-batch", "UNAVAILABLE", "unreachable", url)
        return
    if "response" not in data:
        record("pian-batch", "FAIL",
               f"error body: {json.dumps(data)[:200]}", url)
        return
    docs = data["response"].get("docs", [])
    if not docs:
        record("pian-batch", "FAIL", "0 docs for a known PIAN id batch", url)
        return
    with_wkt = 0
    for d in docs:
        raw = d.get("pian_chranene_udaje")
        if isinstance(raw, list) and raw:
            raw = raw[0]
        jdata = (json.loads(raw) if isinstance(raw, str) else (raw or {}))
        if isinstance(jdata, dict) and (
            jdata.get("geom_sjtsk_wkt") or jdata.get("geom_wkt")
        ):
            with_wkt += 1
    if with_wkt == len(docs):
        record("pian-batch", "OK",
               f"{len(docs)} PIAN docs, all with WKT geometry", url)
    elif with_wkt:
        record("pian-batch", "DRIFT",
               f"{with_wkt}/{len(docs)} PIAN docs with WKT – "
               "records without geometry are skipped by the plugin", url)
    else:
        record("pian-batch", "FAIL",
               "no geom_sjtsk_wkt / geom_wkt in pian_chranene_udaje", url)


def check_filters(docs_by_entity):
    """Every filter key the dialog builds, values from live facets."""
    url = DA_URL + "/api/search/query"
    # (entity, filter key, facet field it draws its value from)
    plan = [
        ("akce", "f_kraj"), ("akce", "f_okres"), ("akce", "f_katastr"),
        ("akce", "f_obdobi"), ("akce", "f_areal"),
        ("akce", "f_pian_presnost"), ("akce", "f_typ_vyzkumu"),
        ("akce", "f_vedouci"), ("akce", "f_organizace"),
        ("lokalita", "f_typ_lokality"), ("lokalita", "f_druh_lokality"),
        ("lokalita", "f_jistota"), ("lokalita", "f_lokalita_zachovalost"),
        ("samostatny_nalez", "f_kategorie"),
        ("samostatny_nalez", "f_druh_nalezu"),
        ("samostatny_nalez", "f_specifikace"),
        ("samostatny_nalez", "f_nalezove_okolnosti"),
        ("samostatny_nalez", "f_nalezce"),
    ]
    for entity, key in plan:
        ff = fetch_facets(entity, bbox=TEST_BBOX)
        if ff is None:
            record(f"filter {entity}.{key}", "UNAVAILABLE", "unreachable",
                   url)
            continue
        items = ff.get(key) or []
        if not items:
            record(f"filter {entity}.{key}", "FAIL",
                   f"no facet values for {key} in the test bbox", url)
            continue
        item = items[0]
        value = item[0] if isinstance(item, list) else item.get("name")
        if not value:
            record(f"filter {entity}.{key}", "FAIL",
                   f"facet item for {key} has no value", url)
            continue
        params = {
            "mapa": "true",
            "sort": "ident_cely asc",
            "entity": entity,
            "rows": 1,
            "loc_rpt": TEST_BBOX,
            key: [f"{value}:or"],
        }
        data = get_json(url, params)
        if data is None:
            record(f"filter {entity}.{key}", "UNAVAILABLE", "unreachable",
                   url)
            continue
        if "response" not in data:
            record(f"filter {entity}.{key}", "FAIL",
                   f"API error for value {value!r}: "
                   f"{json.dumps(data)[:150]}", url)
            continue
        num = data["response"].get("numFound")
        record(f"filter {entity}.{key}", "OK",
               f"value {value!r} accepted, numFound {num}", url)


def check_date_ranges():
    """Date range filter, sent the way the dialog builds it."""
    url = DA_URL + "/api/search/query"
    plan = [
        ("akce", "akce_datum_zahajeni"),
        ("akce", "akce_datum_ukonceni"),
        ("samostatny_nalez", "samostatny_nalez_datum_nalezu"),
    ]
    for entity, field in plan:
        params = {
            "mapa": "true", "sort": "ident_cely asc", "entity": entity,
            "rows": 1, "loc_rpt": TEST_BBOX,
            field: "1900-01-01,2030-12-31",
        }
        data = get_json(url, params)
        if data is None:
            record(f"date {entity}.{field}", "UNAVAILABLE", "unreachable",
                   url)
            continue
        if "response" not in data:
            record(f"date {entity}.{field}", "FAIL",
                   f"error body: {json.dumps(data)[:150]}", url)
            continue
        record(f"date {entity}.{field}", "OK",
               f"numFound {data['response'].get('numFound')}", url)


def check_special_params():
    """pristupnost, posevidence, proj_akce – sent as the dialog sends."""
    url = DA_URL + "/api/search/query"
    plan = [
        ("akce", {"pristupnost": ["A:or"]}),
        ("akce", {"posevidence": "true"}),
        ("akce", {"proj_akce": "true"}),
    ]
    for entity, extra in plan:
        key = list(extra)[0]
        params = {
            "mapa": "true", "sort": "ident_cely asc", "entity": entity,
            "rows": 1, "loc_rpt": TEST_BBOX, **extra
        }
        data = get_json(url, params)
        if data is None:
            record(f"param {entity}.{key}", "UNAVAILABLE", "unreachable",
                   url)
            continue
        if "response" not in data:
            record(f"param {entity}.{key}", "FAIL",
                   f"error body: {json.dumps(data)[:150]}", url)
            continue
        record(f"param {entity}.{key}", "OK",
               f"numFound {data['response'].get('numFound')}", url)


def check_error_answers():
    """Invalid parameter and unknown entity must be an error body, not
    an empty result – the plugin reads the absence of 'response'."""
    url = DA_URL + "/api/search/query"
    data = get_json(url, params={
        "entity": "akce", "akce_datum_zahajeni": "notadate"})
    if data is None:
        record("error invalid-parameter", "UNAVAILABLE", "unreachable", url)
    elif isinstance(data, dict) and data.get("error"):
        record("error invalid-parameter", "OK",
               f"error body: {str(data['error'])[:100]}", url)
    elif isinstance(data, dict) and "response" in data:
        record("error invalid-parameter", "FAIL",
               "invalid date was accepted as a normal response", url)
    else:
        record("error invalid-parameter", "FAIL",
               f"unexpected body: {json.dumps(data)[:150]}", url)

    data = get_json(url, params={"entity": "neexistujici_entity", "rows": 1})
    if data is None:
        record("error unknown-entity", "UNAVAILABLE", "unreachable", url)
    elif isinstance(data, dict) and data.get("error"):
        record("error unknown-entity", "OK",
               f"error body: {str(data['error'])[:100]}", url)
    elif isinstance(data, dict) and "response" in data:
        record("error unknown-entity", "FAIL",
               "unknown entity was accepted as a normal response", url)
    else:
        record("error unknown-entity", "FAIL",
               f"unexpected body: {json.dumps(data)[:150]}", url)


def check_login_error_path():
    """login_to_api with wrong credentials: session None, error 'auth'."""
    url = DA_URL + "/api/user/login"
    # Deliberately wrong, obviously fake credentials – nothing secret.
    wrong_user = "test@example.invalid"
    wrong_login_value = "neutron-failure-horse-battery"
    try:
        resp = SESSION.post(
            url,
            json={"user": wrong_user, "pwd": wrong_login_value},
            timeout=TIMEOUT,
        )
    except requests.exceptions.RequestException as e:
        record("login wrong-credentials", "UNAVAILABLE",
               f"{type(e).__name__}: {e}", url)
        return
    if resp.status_code >= 500:
        record("login wrong-credentials", "UNAVAILABLE",
               f"HTTP {resp.status_code}", url)
        return
    try:
        body = resp.json()
    except ValueError:
        record("login wrong-credentials", "FAIL",
               f"non-JSON body (HTTP {resp.status_code})", url)
        return
    if resp.status_code == 200 and body.get("error"):
        record("login wrong-credentials", "OK",
               f"error body: {str(body['error'])[:80]}", url)
    elif resp.status_code in (401, 403):
        record("login wrong-credentials", "OK",
               f"HTTP {resp.status_code}", url)
    else:
        record("login wrong-credentials", "FAIL",
               f"wrong credentials accepted (HTTP {resp.status_code}, "
               f"body {json.dumps(body)[:120]})", url)


def write_outputs():
    """results JSON + Markdown table to stdout and GITHUB_STEP_SUMMARY."""
    path = f"results-{JOB}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(RESULTS, f, ensure_ascii=False, indent=2)
    lines = ["| check | status | detail |", "|---|---|---|"]
    for r in RESULTS:
        detail = str(r["detail"]).replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {r['name']} | {r['status']} | {detail} |")
    table = "\n".join(lines)
    print()
    print(table)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(table + "\n")
    print()
    print(f"written: {path}")
    bad = [r for r in RESULTS if r["status"] in ("FAIL", "DRIFT")]
    print(f"checks: {len(RESULTS)}, FAIL/DRIFT: {len(bad)}")
    return 1 if bad else 0


def main():
    print(f"API contract test against {DA_URL}")
    print(f"test bbox: {TEST_BBOX} (Mikulov)")
    load_deployed_version()
    check_translations()
    docs_by_entity = check_main_queries()
    check_numfound_int()
    check_facet_sets()
    check_oai_sets()
    check_pagination()
    check_bbox_restriction()
    check_pian_batch(docs_by_entity)
    check_filters(docs_by_entity)
    check_date_ranges()
    check_special_params()
    check_error_answers()
    check_login_error_path()
    return write_outputs()


if __name__ == "__main__":
    sys.exit(main())
