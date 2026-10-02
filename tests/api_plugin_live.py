# -*- coding: utf-8 -*-
"""
Live plugin test – calls the plugin's own functions against the live AMČR
API inside a real (headless) QGIS and checks they still produce non-empty,
well-formed results. Where the contract test says *what* changed, this test
says *whether users break*.

It is the API-sensitive counterpart of tests/smoke_test.py, which is
deliberately offline.

Run it from the repository root inside the qgis/qgis Docker image
(requests is bundled with QGIS):

    docker run --rm -v "$PWD:/work:ro" -w /work \
      --user "$(id -u):$(id -g)" -e HOME=/tmp \
      -e AMCR_RESULTS_DIR=/tmp/results \
      qgis/qgis:ltr python3 tests/api_plugin_live.py

The plugin package is imported as a package (amcr_viewer.amcr_tools), so
its relative imports work – a bare spec_from_file_location would make
load_amcr_data swallow the import error into "0 records".

Status model and outputs match tests/api_contract.py: OK / DRIFT / FAIL /
UNAVAILABLE per check, results-plugin_live.json + a Markdown table on
stdout and in $GITHUB_STEP_SUMMARY, exit 1 on any FAIL or DRIFT. A run
where everything is UNAVAILABLE is green but visible in the summary.

Test area (probe 2026-10-02, anonymous): the same Mikulov bbox as the
contract test, 48.8,16.6,48.9,16.75 – akce 185, lokalita 18,
samostatny_nalez 2, pian 294 records. The fake canvas extent uses it
directly in EPSG:4326, so no coordinate transformation is involved.

Thresholds (design decision 6):
  * fetch_set per codelist set: >= 1 item and >= 50 % of that category's
    row count in the bundled codelists/heslar.csv (a shrunken codelist is
    the #67 symptom)
  * load_amcr_data per data type: >= 1 layer with >= 1 feature, valid
    geometry and the expected attribute fields

Env overrides (outage simulation; the plugin's own URLs are hard-coded,
so the overrides only steer the availability probe and the codelist
sets, whose URLs live in a module dict). An unreachable host fails fast:
after the full retry cycle of the first probe, later probes to the same
host do no network I/O:
  AMCR_DA_URL    digiarchiv base URL (default
                  https://digiarchiv.aiscr.cz)
  AMCR_OAI_URL   AMCR OAI base URL (default
                  https://api.aiscr.cz/2.2/oai)
  AMCR_TIMEOUT   per-request timeout in seconds (default 15)
"""

import csv
import json
import os
import sys
import traceback

# Offscreen, otherwise the widgets would need an X server
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

RESULTS_DIR = os.environ.get("AMCR_RESULTS_DIR", os.getcwd())
DA_URL = os.environ.get("AMCR_DA_URL", "https://digiarchiv.aiscr.cz")
OAI_URL = os.environ.get("AMCR_OAI_URL", "https://api.aiscr.cz/2.2/oai")
TIMEOUT = int(os.environ.get("AMCR_TIMEOUT", "15"))
TEST_BBOX = "48.8,16.6,48.9,16.75"  # minLat,minLon,maxLat,maxLon (Mikulov)
BBOX_MIN_LAT, BBOX_MIN_LON, BBOX_MAX_LAT, BBOX_MAX_LON = (
    float(x) for x in TEST_BBOX.split(",")
)

RESULTS = []
JOB = "plugin_live"
UNAVAILABLE_DA = False
UNAVAILABLE_OAI = False


def record(name, status, detail):
    RESULTS.append({"name": name, "status": status, "detail": detail,
                    "url": ""})
    print(f"  {status:<12} {name} – {detail}")


import requests  # noqa: E402

# ---------------------------------------------------------------- QGIS setup
from qgis.core import (  # noqa: E402
    Qgis,
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsProject,
    QgsRectangle,
)

print(f"QGIS {Qgis.QGIS_VERSION.split('-')[0]}")
QgsApplication.setPrefixPath(os.environ.get("QGIS_PREFIX_PATH", "/usr"),
                             True)
qgs = QgsApplication([], True)
qgs.initQgis()

import amcr_viewer.amcr_codelists as codelists  # noqa: E402
import amcr_viewer.amcr_tools as tools  # noqa: E402

# Point the codelist sets at the overridden base URLs (outage simulation).
# The data-download URL inside load_amcr_data is hard-coded and cannot be
# steered from here; when the probe says digiarchiv is unreachable, the
# download checks are reported UNAVAILABLE without calling the plugin.
if DA_URL != "https://digiarchiv.aiscr.cz" \
        or OAI_URL != "https://api.aiscr.cz/2.2/oai":
    _new = {}
    for key, (base, api_set) in codelists.slovnicek.items():
        if "digiarchiv" in base:
            base = DA_URL + "/api/search/query"
        else:
            base = OAI_URL
        _new[key] = (base, api_set)
    codelists.slovnicek.clear()
    codelists.slovnicek.update(_new)


# ------------------------------------------------------------------ fakes
class FakeMessageBar:
    """Collects messageBar() messages so failures can be diagnosed."""

    def __init__(self):
        self.messages = []

    def pushMessage(self, title, text, level=Qgis.MessageLevel.Info):
        self.messages.append((title, str(text), level))


class FakeIface:
    def __init__(self):
        self._bar = FakeMessageBar()

    def messageBar(self):
        return self._bar

    def mapCanvas(self):
        return fake_canvas


class FakeMapSettings:
    def __init__(self, crs):
        self._crs = crs

    def destinationCrs(self):
        return self._crs


class FakeCanvas:
    """Map canvas whose extent is the test bbox in EPSG:4326."""

    def __init__(self):
        self._extent = QgsRectangle(
            BBOX_MIN_LON, BBOX_MIN_LAT, BBOX_MAX_LON, BBOX_MAX_LAT
        )
        self._settings = FakeMapSettings(
            QgsCoordinateReferenceSystem("EPSG:4326"))

    def extent(self):
        return self._extent

    def mapSettings(self):
        return self._settings


fake_canvas = FakeCanvas()
fake_iface = FakeIface()

# amcr_tools does "from qgis.utils import iface", which binds None in a
# headless run – patch the module attribute, not qgis.utils
tools.iface = fake_iface


# ------------------------------------------------------------------ checks
# Circuit breaker (fast outage), the same as in tests/api_contract.py:
# once a host (netloc) is unreachable after full retries, later probes to
# it return False without network I/O, so an all-unreachable run finishes
# in seconds instead of tens of minutes.
DEAD_HOSTS = set()


def probe(url, params=None):
    """Availability probe with retries; True when the API answers.

    Once a host is found unreachable after the full retry cycle, it is
    added to DEAD_HOSTS and later probes to it fail immediately.
    """
    import time
    import urllib.parse
    netloc = urllib.parse.urlparse(url).netloc
    if netloc in DEAD_HOSTS:
        return False
    for attempt in range(3):
        try:
            resp = requests.get(url, params=params, timeout=TIMEOUT)
            if resp.status_code < 500:
                return True
        except requests.exceptions.RequestException:
            pass
        if attempt < 2:
            time.sleep((2, 8)[attempt])
    DEAD_HOSTS.add(netloc)
    return False


def bundled_counts():
    """Row count per category in the bundled codelists/heslar.csv."""
    path = os.path.join(ROOT, "amcr_viewer", "codelists", "heslar.csv")
    counts = {}
    # utf-8-sig: the CSV carries a BOM on purpose (Excel)
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f, delimiter=";"):
            cat = (row.get("Kategorie") or "").strip()
            if cat:
                counts[cat] = counts.get(cat, 0) + 1
    return counts


def check_translations():
    if UNAVAILABLE_DA:
        record("load_translations", "UNAVAILABLE",
               "digiarchiv unreachable after retries")
        return
    tools.TRANSLATIONS.clear()
    try:
        tools.load_translations()
    except Exception:
        record("load_translations", "FAIL",
               traceback.format_exc().rstrip().splitlines()[-1])
        return
    if tools.TRANSLATIONS:
        record("load_translations", "OK",
               f"{len(tools.TRANSLATIONS)} keys")
    else:
        record("load_translations", "FAIL",
               "TRANSLATIONS stayed empty after load_translations()")


def check_fetch_set():
    """fetch_set per set in slovnicek against the live API."""
    bundled = bundled_counts()
    for name, (base_url, api_set) in codelists.slovnicek.items():
        unavailable = (UNAVAILABLE_OAI if "digiarchiv" not in base_url
                       else UNAVAILABLE_DA)
        if unavailable:
            record(f"fetch_set {name}", "UNAVAILABLE",
                   "API unreachable after retries")
            continue
        try:
            data = codelists.fetch_set(base_url, name, api_set)
        except Exception:
            record(f"fetch_set {name}", "FAIL",
                   traceback.format_exc().rstrip().splitlines()[-1])
            continue
        if data is None:
            record(f"fetch_set {name}", "FAIL", "cancelled (task)")
            continue
        if not data:
            record(f"fetch_set {name}", "FAIL",
                   f"set {api_set} returned 0 items – the #67 symptom")
            continue
        expected = bundled.get(name, 0)
        if expected and len(data) < expected * 0.5:
            record(f"fetch_set {name}", "FAIL",
                   f"{len(data)} items < 50 % of {expected} bundled rows "
                   "– a shrunken codelist is the #67 symptom")
        else:
            record(f"fetch_set {name}", "OK",
                   f"{len(data)} items"
                   + (f" (bundled: {expected})" if expected else ""))


def _layer_specs(typ_dat):
    """Expected attribute fields per data type, from amcr_tools.py."""
    common = ["pian", "presnost", "pian_typ", "dj", "typ_dj", typ_dat,
              "definicni_body", "odkaz_do_digiarchivu", "okres", "katastr",
              "dalsi_katastry", "pristupnost"]
    if typ_dat == "akce":
        common += ["akce_lokalizace", "vedouci", "organizace",
                   "specifikace_data", "zahajeni", "ukonceni",
                   "hlavni_typ", "vedlejsi_typ", "zjisteni",
                   "nahrazuje_NZ", "projekt"]
    elif typ_dat == "lokalita":
        common += ["nazev_lokality", "popis_lokality", "typ_lokality",
                   "druh_lokality", "zachovalost"]
    elif typ_dat == "samostatny_nalez":
        common = [typ_dat, "definicni_body", "odkaz_do_digiarchivu",
                  "okres", "katastr", "dalsi_katastry", "projekt",
                  "nalezce", "datum", "okolnosti", "hloubka_cm",
                  "lokalizace", "obdobi", "presna_datace", "nalez",
                  "material", "pocet", "poznamka", "pred_org",
                  "evidencni", "pristupnost"]
    return common


def check_load_amcr_data():
    """load_amcr_data per data type on the test bbox (fake iface/canvas).

    The call is synchronous in the main thread (load_amcr_data pumps the
    event loop itself, it is not a QgsTask), so a plain call is enough.
    """
    for typ_dat in ["akce", "lokalita", "samostatny_nalez"]:
        if UNAVAILABLE_DA:
            record(f"load_amcr_data {typ_dat}", "UNAVAILABLE",
                   "digiarchiv unreachable after retries")
            continue
        # Layers from a previous data type must not mix into the check
        project = QgsProject.instance()
        project.removeAllMapLayers()
        try:
            tools.load_amcr_data(fake_canvas, "true", None,
                                 typ_dat=typ_dat, komponenty="false")
        except Exception:
            record(f"load_amcr_data {typ_dat}", "FAIL",
                   traceback.format_exc().rstrip().splitlines()[-1])
            continue
        layers = [lyr for lyr in project.mapLayers().values()
                  if "amcr_" in lyr.name().lower()]
        if not layers:
            record(f"load_amcr_data {typ_dat}", "FAIL",
                   "no AMCR layers were added to the project; messageBar: "
                   + "; ".join(m[1] for m in fake_iface._bar.messages[-3:]))
            continue
        total_features = sum(lyr.featureCount() for lyr in layers)
        if total_features < 1:
            record(f"load_amcr_data {typ_dat}", "FAIL",
                   f"{len(layers)} layers but 0 features")
            continue
        # valid geometry + expected fields on the populated layers
        problems = []
        expected_fields = _layer_specs(typ_dat)
        for layer in layers:
            if layer.featureCount() == 0:
                continue
            fields = {f.name() for f in layer.fields()}
            missing = [fl for fl in expected_fields if fl not in fields]
            if missing:
                problems.append(f"{layer.name()}: missing fields "
                                f"{missing}")
            for feat in layer.getFeatures():
                geom = feat.geometry()
                if (geom is None or geom.isNull()
                        or not geom.isGeosValid()):
                    problems.append(f"{layer.name()}: invalid geometry")
                    break
        if problems:
            record(f"load_amcr_data {typ_dat}", "FAIL",
                   "; ".join(problems))
        else:
            record(f"load_amcr_data {typ_dat}", "OK",
                   f"{len(layers)} layers, {total_features} features, "
                   "fields and geometry valid")


def write_outputs():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    path = os.path.join(RESULTS_DIR, f"results-{JOB}.json")
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
    global UNAVAILABLE_DA, UNAVAILABLE_OAI
    print("live plugin test against the production AMČR API")
    print(f"test bbox: {TEST_BBOX} (Mikulov)")
    UNAVAILABLE_DA = not probe(
        DA_URL + "/api/search/query", params={"entity": "akce", "rows": 0})
    UNAVAILABLE_OAI = not probe(
        OAI_URL, params={"verb": "Identify"})
    if UNAVAILABLE_DA:
        print("digiarchiv unreachable after retries")
    if UNAVAILABLE_OAI:
        print("AMČR OAI unreachable after retries")
    check_translations()
    check_fetch_set()
    check_load_amcr_data()
    qgs.exitQgis()
    return write_outputs()


if __name__ == "__main__":
    sys.exit(main())
