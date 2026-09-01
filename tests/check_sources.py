# -*- coding: utf-8 -*-
"""
Repository hygiene rules that need no QGIS and therefore run first.

Each rule guards a mistake that has already happened here at least once,
or one the plugins.qgis.org file analysis reports:

* a UTF-8 BOM makes the official pyqgis4-checker skip the file entirely,
  so a broken file looks clean – it is silent, which is what makes it bad
* a direct PyQt5/PyQt6 import breaks the other Qt version
* an executable or hidden file in the package is reported on upload

Run it from the repository root:

    python3 tests/check_sources.py
"""

import os
import re
import stat
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BALICEK = os.path.join(ROOT, "amcr_viewer")

# Files that belong in the plugin package even though the upload scanner
# would otherwise call them hidden
POVOLENE_SKRYTE = {".flake8", ".bandit", ".secrets.baseline"}

# Extensions that have no business inside a plugin package
PODEZRELE = {".exe", ".dll", ".so", ".dylib", ".sh", ".bat", ".cmd",
             ".pyc", ".pyd", ".jar", ".bin"}

PRIMY_IMPORT = re.compile(r"^\s*(?:from|import)\s+PyQt[56]\b", re.MULTILINE)

nalezy = []


def zdrojaky():
    for adresar, _, soubory in os.walk(BALICEK):
        for soubor in sorted(soubory):
            if soubor.endswith(".py"):
                yield os.path.join(adresar, soubor)


def vsechny_soubory():
    for adresar, _, soubory in os.walk(BALICEK):
        for soubor in sorted(soubory):
            yield os.path.join(adresar, soubor)


def zkratka(cesta):
    return os.path.relpath(cesta, ROOT)


for cesta in zdrojaky():
    with open(cesta, "rb") as f:
        zacatek = f.read(3)
    if zacatek == b"\xef\xbb\xbf":
        nalezy.append(f"{zkratka(cesta)}: UTF-8 BOM na začátku souboru")

    with open(cesta, encoding="utf-8-sig") as f:
        text = f.read()
    for shoda in PRIMY_IMPORT.finditer(text):
        radek = text[:shoda.start()].count("\n") + 1
        nalezy.append(f"{zkratka(cesta)}:{radek}: přímý import z PyQt5/PyQt6, "
                      f"použij shim qgis.PyQt")

for cesta in vsechny_soubory():
    jmeno = os.path.basename(cesta)
    rezim = os.stat(cesta).st_mode
    if rezim & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH):
        nalezy.append(f"{zkratka(cesta)}: spustitelná práva "
                      f"({stat.filemode(rezim)})")
    if jmeno.startswith(".") and jmeno not in POVOLENE_SKRYTE:
        nalezy.append(f"{zkratka(cesta)}: skrytý soubor v balíčku pluginu")
    if os.path.splitext(jmeno)[1].lower() in PODEZRELE:
        nalezy.append(f"{zkratka(cesta)}: podezřelý typ souboru")

if nalezy:
    print("Nálezy:")
    for nalez in nalezy:
        print(f"  {nalez}")
    sys.exit(1)
print("Kontrola zdrojáků: bez nálezů")
