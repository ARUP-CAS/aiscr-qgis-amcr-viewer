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


zkouska("scoped enumy", enumy)
zkouska("UpdateCodelistsTask", uloha)
zkouska("filtrační dialogy", dialogy)
zkouska("filtr podle data", filtr_datumu)

qgs.exitQgis()

if selhani:
    print(f"\nNEPROŠLO: {', '.join(selhani)}")
    sys.exit(1)
print("\nVše prošlo")
