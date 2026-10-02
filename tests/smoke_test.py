# -*- coding: utf-8 -*-
"""
Smoke test: loads the plugin inside a real QGIS and exercises the parts
that differ between Qt5 and Qt6.

It is deliberately offline – no request ever leaves the machine, so the
test says nothing about the AMCR API, only about the plugin loading and
its widgets being constructible.

Run it from the repository root:

    python3 tests/smoke_test.py

QGIS must be importable (inside the qgis/qgis Docker image it already is).
The exit code is 0 when everything passed, 1 otherwise.
"""

import os
import sys
import traceback

import requests

# Offscreen, otherwise the dialogs need an X server
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

selhani = []


def zkouska(nazev, funkce):
    """Runs one check and keeps going even when it raises."""
    try:
        detail = funkce()
    except Exception:
        selhani.append(nazev)
        print(f"  FAIL  {nazev}")
        print(traceback.format_exc().rstrip())
    else:
        print(f"  OK    {nazev}" + (f" – {detail}" if detail else ""))


from qgis.core import (  # noqa: E402
    Qgis,
    QgsApplication,
    QgsTask,
    QgsWkbTypes,
)
from qgis.PyQt import QtCore  # noqa: E402
from qgis.PyQt.QtCore import QDate  # noqa: E402

print(f"QGIS {Qgis.QGIS_VERSION.split('-')[0]} | Qt {QtCore.QT_VERSION_STR} "
      f"| PyQt {QtCore.PYQT_VERSION_STR}")

QgsApplication.setPrefixPath(os.environ.get("QGIS_PREFIX_PATH", "/usr"), True)
qgs = QgsApplication([], True)
qgs.initQgis()

import amcr_viewer.amcr_codelists  # noqa: E402,F401
import amcr_viewer.amcr_dialog as dialog  # noqa: E402
import amcr_viewer.amcr_tools  # noqa: E402,F401
import amcr_viewer.amcr_viewer  # noqa: E402,F401

print("  OK    import všech modulů pluginu")


def enumy():
    """
    The scoped enum forms must exist. Unscoped aliases still resolve in
    QGIS 4.2, so a plain import proves nothing – these are read explicitly.
    """
    return (f"QgsTask.Flag.CanCancel={int(QgsTask.Flag.CanCancel)}, "
            f"PointGeometry={int(QgsWkbTypes.GeometryType.PointGeometry)}, "
            f"MessageLevel.Info={int(Qgis.MessageLevel.Info)}")


def uloha():
    ukol = dialog.UpdateCodelistsTask("smoke")
    assert ukol.canCancel() is True
    return "canCancel=True"


def dialogy():
    # A modal warning would block the offscreen run forever
    dialog.QMessageBox.warning = staticmethod(lambda *a, **k: None)
    popis = []
    for typ in ("akce", "lokalita", "samostatny_nalez"):
        okno = dialog.AmcrFilterDialog(typ)
        okno.show()
        QgsApplication.processEvents()
        popis.append(f"{typ}: {len(okno.date_ranges)} rozmezí")
        okno.close()
    return ", ".join(popis)


def filtr_datumu():
    """
    A half-filled range must be completed with the sentinel. The API
    rejects a one-sided range, so this is the part worth guarding.

    The expected value is written out on purpose – comparing against
    dialog.DATE_OPEN_TO would only prove the module agrees with itself.
    """
    okno = dialog.AmcrFilterDialog("samostatny_nalez")
    pole, _, od, _do = okno.date_ranges[0]
    od.setDate(QDate(2016, 1, 1))
    hodnota = okno.get_filters()[pole]
    assert hodnota == "2016-01-01,9999-12-31", hodnota

    # A range left completely empty must add no filter at all
    prazdne = dialog.AmcrFilterDialog("samostatny_nalez")
    pole_prazdne = prazdne.date_ranges[0][0]
    assert pole_prazdne not in prazdne.get_filters()
    prazdne.close()

    okno.close()
    return hodnota


class FalesnaSession:
    """Offline stand-in for requests.Session: returns canned JSON
    bodies for GET /api/user/islogged and counts the requests."""

    def __init__(self, tela):
        # tela: a list of (body, exception) pairs – one per GET call,
        # consumed in order; None body means raise the exception
        self.tela = list(tela)
        self.get_volani = 0

    def get(self, url, timeout=0):
        self.get_volani += 1
        polozka = self.tela.pop(0)
        # A bare dict is a plain body; (None, exception) means raise
        if isinstance(polozka, tuple):
            tela, vyjimka = polozka
        else:
            tela, vyjimka = polozka, None
        if tela is None and vyjimka is not None:
            raise vyjimka

        class Odpoved:
            def __init__(self, tela):
                self.telo = tela
                self.text = str(tela)

            def json(self):
                if isinstance(self.telo, Exception):
                    raise self.telo
                return self.telo

        return Odpoved(tela)


def prihlasovaci_stav():
    """
    _ensure_logged_in with a fake session and monkeypatched login /
    credentials / _get_session – everything stays offline.

    Each case: (name, expected status, islogged bodies of the current
    session, islogged bodies after re-login, fake login result,
    stored credentials, expected number of islogged GETs).
    """
    pripady = [
        # Valid session – no re-login, no extra request
        ("platná session", "logged_in",
         [{"remaining": 3500}], [], None, ("", ""), 1),
        # nologged + successful re-login, verified again
        ("expired + re-login", "relogged",
         [{"error": "nologged"}], [{"remaining": 1800}],
         "session", ("uzivatel", "heslo"), 1),
        # nologged + failed re-login
        ("expired + selhaný re-login", "fallback",
         [{"error": "nologged"}], [], None, ("uzivatel", "heslo"), 1),
        # nologged + no stored credentials
        ("expired bez údajů", "fallback",
         [{"error": "nologged"}], [], None, ("", ""), 1),
        # No session and no credentials – no request at all
        ("anonym bez údajů", "anonymous",
         [], [], None, ("", ""), 0),
        # Network error during the check
        ("chyba sítě", "unknown",
         [(None, requests.exceptions.ConnectionError("probe"))],
         [], None, ("", ""), 1),
        # 200 but invalid JSON
        ("neplatný JSON", "unknown",
         [(None, ValueError("Invalid JSON"))],
         [], None, ("", ""), 1),
    ]

    tools = amcr_viewer.amcr_tools
    puvodni = (tools.login_to_api, tools._get_session,
               dialog.LoginDialog.__dict__["get_credentials"])
    try:
        return _prihlasovaci_stav(pripady, tools)
    finally:
        # Leave the modules as they were found, even when a case fails
        (tools.login_to_api, tools._get_session,
         dialog.LoginDialog.get_credentials) = puvodni
        tools.AMCR_SESSION = None


def _prihlasovaci_stav(pripady, tools):
    """Runs the cases of prihlasovaci_stav()."""
    vysledky = []
    for (nazev, ocekavano, tela, tela_po_loginu, login_vysledek,
         kredity, get_volani) in pripady:

        # The current session (None = _get_session returns None);
        # a successful fake re-login produces a new fake session
        session = FalesnaSession(tela) if tela else None
        login_hodnota = FalesnaSession(tela_po_loginu) \
            if login_vysledek else None

        tools.AMCR_SESSION = session

        def fake_login(hodnota):
            # Like the real login_to_api: stores the session globally
            def login(uzivatel, heslo):
                if hodnota is not None:
                    tools.AMCR_SESSION = hodnota
                return hodnota
            return login

        tools.login_to_api = fake_login(login_hodnota)
        tools._get_session = (lambda s: lambda: s)(session) \
            if session else (lambda: None)
        dialog.LoginDialog.get_credentials = staticmethod(
            (lambda k: lambda: k)(kredity)
        )

        stav = tools._ensure_logged_in()
        assert stav == ocekavano, f"{nazev}: {stav} != {ocekavano}"

        # The old session object must have been used for the checks
        if session is not None:
            assert session.get_volani == get_volani, \
                f"{nazev}: {session.get_volani} != {get_volani}"

        # The returned fake login session must become the global one
        # and its login state must have been verified as well
        if ocekavano == "relogged":
            assert login_hodnota is not None
            assert tools.AMCR_SESSION is login_hodnota
            assert login_hodnota.get_volani == 1, \
                f"{nazev}: nová session nebyla ověřena"

        vysledky.append(f"{nazev} → {stav}")

    return ", ".join(vysledky)


def odhlaseni():
    """logout_from_api with a fake session – offline."""
    tools = amcr_viewer.amcr_tools
    puvodni = tools.AMCR_SESSION
    try:
        # Logged-in session: one GET to /logout, session dropped
        session = FalesnaSession([{"msg": "logged out"}])
        session_get = session.get
        urls = []

        def get(url, timeout=0):
            urls.append(url)
            odpoved = session_get(url, timeout)
            odpoved.raise_for_status = lambda: None
            return odpoved

        session.get = get
        tools.AMCR_SESSION = session
        assert tools.logout_from_api() is True
        assert tools.AMCR_SESSION is None
        assert urls and urls[0].endswith("/api/user/logout"), urls

        # Network error: session still dropped locally
        chyba = FalesnaSession(
            [(None, requests.exceptions.ConnectionError("probe"))]
        )
        tools.AMCR_SESSION = chyba
        assert tools.logout_from_api() is False
        assert tools.AMCR_SESSION is None
        assert chyba.get_volani == 1

        # No session: nothing to do, no request
        assert tools.logout_from_api() is True
    finally:
        tools.AMCR_SESSION = puvodni
    return "odhlášení, chyba sítě → zahozeno lokálně, bez session → nic"


def vaha_komponent():
    """
    _component_entries: the weight is 1/n of the components that pass
    the predicate, so the weights of one documentation unit sum to 1
    even with a period/area filter active.

    The cases come from the spec of the fix (issue #55); the sums are
    compared with a tolerance because 1/3 weights add up to 0.999…
    """
    tools = amcr_viewer.amcr_tools

    def komponenta(ident, areal=None, obdobi=None):
        return {
            "ident_cely": ident,
            "komponenta_areal": ({"id": areal} if areal else None),
            "komponenta_obdobi": ({"id": obdobi} if obdobi else None),
        }

    dj_meta = {"dj_id": "X-M-000001"}

    # 4 components, no filter: 4 features, each 0.25
    komps = [komponenta(f"K{i}") for i in range(4)]
    zaznamy = tools._component_entries(dj_meta, komps, lambda k: True)
    assert len(zaznamy) == 4, len(zaznamy)
    assert all(z["vaha"] == 0.25 for z in zaznamy), \
        [z["vaha"] for z in zaznamy]

    # Period filter keeps 1 of 4: single feature with weight 1
    komps = [
        komponenta("K0", obdobi="neolit"),
        komponenta("K1"), komponenta("K2"), komponenta("K3"),
    ]
    zaznamy = tools._component_entries(
        dj_meta, komps, lambda k: k["komponenta_obdobi"] is not None
    )
    assert len(zaznamy) == 1, len(zaznamy)
    assert zaznamy[0]["vaha"] == 1.0, zaznamy[0]["vaha"]

    # Filter keeps 2 of 3: 2 features, each 0.5, sum 1 within tolerance
    komps = [
        komponenta("K0", obdobi="neolit"), komponenta("K1", obdobi="bronz"),
        komponenta("K2"),
    ]
    zaznamy = tools._component_entries(
        dj_meta, komps, lambda k: k["komponenta_obdobi"] is not None
    )
    assert len(zaznamy) == 2, len(zaznamy)
    assert all(z["vaha"] == 0.5 for z in zaznamy), \
        [z["vaha"] for z in zaznamy]
    assert abs(sum(z["vaha"] for z in zaznamy) - 1) < 1e-9

    # Sum with tolerance also for an indivisible split (1/3)
    komps = [komponenta(f"K{i}") for i in range(3)]
    zaznamy = tools._component_entries(dj_meta, komps, lambda k: True)
    assert abs(sum(z["vaha"] for z in zaznamy) - 1) < 1e-9

    # No components: one entry with empty component fields, weight 1
    zaznamy = tools._component_entries(dj_meta, [], lambda k: True)
    assert len(zaznamy) == 1, zaznamy
    assert zaznamy[0]["vaha"] == 1, zaznamy[0]["vaha"]
    assert zaznamy[0]["komponenta_id"] == ""

    # The shared DJ metadata and component fields travel along
    komps = [komponenta("K0", areal="sidelni", obdobi="neolit")]
    zaznamy = tools._component_entries(dj_meta, komps, lambda k: True)
    assert zaznamy[0]["dj_id"] == "X-M-000001"
    assert zaznamy[0]["komponenta_id"] == "K0"

    return "4×0.25; 1/4 → 1.0; 2/3 → 2×0.5; prázdné → 1"


zkouska("scoped enumy", enumy)
zkouska("UpdateCodelistsTask", uloha)
zkouska("filtrační dialogy", dialogy)
zkouska("filtr podle data", filtr_datumu)
zkouska("stav přihlášení", prihlasovaci_stav)
zkouska("odhlášení", odhlaseni)
zkouska("váha komponent", vaha_komponent)

qgs.exitQgis()

if selhani:
    print(f"\nNEPROŠLO: {', '.join(selhani)}")
    sys.exit(1)
print("\nVše prošlo")
