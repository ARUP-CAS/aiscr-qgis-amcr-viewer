# -*- coding: utf-8 -*-
"""
Guards the release PR (version/vX.Y.Z -> main).

Checks that the version actually moved forward and that the three places
that name it agree, because plugins.qgis.org and Zenodo both read from
files a human has to remember to touch by hand:

* amcr_viewer/metadata.txt: version= must be higher than on main, and the
  first changelog entry must be for that exact version
* CITATION.cff: version must match metadata.txt, and date-released must
  not be left pointing at the old release
* the branch name (version/vX.Y.Z) must match metadata.txt, so a stray
  push to the wrong release branch is caught before merge

Run from the repository root:

    python3 tests/check_version_bump.py <base_sha> <head_ref>
"""

import datetime
import re
import subprocess
import sys

METADATA = "amcr_viewer/metadata.txt"
CITATION = "CITATION.cff"

VERZE_METADATA = re.compile(r"^version=(.+)$", re.MULTILINE)
VERZE_CITATION = re.compile(r"^version:\s*'?([^'\n]+)'?\s*$", re.MULTILINE)
DATUM_CITATION = re.compile(r"^date-released:\s*'?([^'\n]+)'?\s*$",
                             re.MULTILINE)
# Přeskočí úvodní řádek "Plný seznam změn ... /vX.Y.Z" a najde první
# skutečnou položku changelogu.
POLOZKA_CHANGELOGU = re.compile(r"^\s+v([0-9][^\s(]*)\s*\(", re.MULTILINE)
BRANCH_VERZE = re.compile(r"^version/v(.+)$")

nalezy = []


def nacti_na_base(base_sha, cesta):
    vysledek = subprocess.run(
        ["git", "show", f"{base_sha}:{cesta}"],
        capture_output=True, text=True,
    )
    if vysledek.returncode != 0:
        nalezy.append(f"{cesta}: na cílové větvi nejde přečíst "
                       f"(git show {base_sha}:{cesta} selhalo)")
        return None
    return vysledek.stdout


def nacti(cesta):
    with open(cesta, encoding="utf-8") as f:
        return f.read()


def hledej(vzor, text, cesta, popis):
    shoda = vzor.search(text)
    if not shoda:
        nalezy.append(f"{cesta}: {popis} nenalezeno")
        return None
    return shoda.group(1).strip()


def verze_tuple(verze):
    jadro = verze.split("-", 1)[0]
    try:
        return tuple(int(c) for c in jadro.split("."))
    except ValueError:
        return None


def je_bump(stara, nova):
    if stara == nova:
        return False
    stara_t, nova_t = verze_tuple(stara), verze_tuple(nova)
    if stara_t is None or nova_t is None:
        # Nestandardní formát verze – nejde spolehlivě porovnat čísly,
        # stačí tedy, že se řetězec liší.
        return True
    if nova_t != stara_t:
        return nova_t > stara_t
    # Stejné jádro (např. "-alpha" přípona): bump platí, pokud se text
    # liší a nejde o couvnutí z release na prerelease.
    return "-" in stara or "-" not in nova


def datum(text):
    try:
        return datetime.date.fromisoformat(text)
    except ValueError:
        return None


def main():
    if len(sys.argv) != 3:
        print("použití: check_version_bump.py <base_sha> <head_ref>")
        return 2
    base_sha, head_ref = sys.argv[1], sys.argv[2]

    base_metadata = nacti_na_base(base_sha, METADATA)
    base_citation = nacti_na_base(base_sha, CITATION)
    head_metadata = nacti(METADATA)
    head_citation = nacti(CITATION)

    if base_metadata is None or base_citation is None:
        # Bez base souborů nejde nic dalšího smysluplně ověřit.
        print("Nálezy:")
        for nalez in nalezy:
            print(f"  {nalez}")
        return 1

    stara_verze = hledej(VERZE_METADATA, base_metadata, METADATA,
                          "verze na cílové větvi (version=)")
    nova_verze = hledej(VERZE_METADATA, head_metadata, METADATA,
                         "verze (version=)")
    stara_citation_verze = hledej(VERZE_CITATION, base_citation, CITATION,
                                   "verze na cílové větvi (version:)")
    nova_citation_verze = hledej(VERZE_CITATION, head_citation, CITATION,
                                  "verze (version:)")
    stare_datum = hledej(DATUM_CITATION, base_citation, CITATION,
                          "date-released na cílové větvi")
    nove_datum = hledej(DATUM_CITATION, head_citation, CITATION,
                         "date-released")

    if None in (stara_verze, nova_verze, stara_citation_verze,
                nova_citation_verze, stare_datum, nove_datum):
        print("Nálezy:")
        for nalez in nalezy:
            print(f"  {nalez}")
        return 1

    # 1. metadata.txt: verze musí jít dopředu.
    if not je_bump(stara_verze, nova_verze):
        nalezy.append(
            f"{METADATA}: verze nepovýšena ({stara_verze} -> {nova_verze})")

    # 2. metadata.txt: první položka changelogu musí patřit nové verzi.
    prvni_polozka = POLOZKA_CHANGELOGU.search(head_metadata)
    if not prvni_polozka:
        nalezy.append(f"{METADATA}: v changelog= nenalezena žádná položka "
                       f"'vX.Y.Z (...)'")
    elif prvni_polozka.group(1) != nova_verze:
        nalezy.append(
            f"{METADATA}: první položka changelogu je pro "
            f"v{prvni_polozka.group(1)}, ale version={nova_verze}")

    # 3. CITATION.cff: verze musí souhlasit s metadata.txt.
    if nova_citation_verze != nova_verze:
        nalezy.append(
            f"{CITATION}: version: {nova_citation_verze} neodpovídá "
            f"{METADATA} version={nova_verze}")

    # 4. CITATION.cff: date-released se musí posunout, a ne dozadu.
    stary_datum_obj, novy_datum_obj = datum(stare_datum), datum(nove_datum)
    if stary_datum_obj is None or novy_datum_obj is None:
        nalezy.append(f"{CITATION}: date-released není platné datum "
                       f"ISO 8601 ({stare_datum!r} -> {nove_datum!r})")
    elif novy_datum_obj < stary_datum_obj:
        nalezy.append(
            f"{CITATION}: date-released couvlo ({stare_datum} -> "
            f"{nove_datum})")
    elif nove_datum == stare_datum and stara_citation_verze != nova_citation_verze:
        nalezy.append(
            f"{CITATION}: version se změnila, ale date-released zůstalo "
            f"na {stare_datum}")

    # 5. Název release větve musí odpovídat verzi, kterou nese.
    shoda_branch = BRANCH_VERZE.match(head_ref)
    if shoda_branch and shoda_branch.group(1) != nova_verze:
        nalezy.append(
            f"větev {head_ref!r} neodpovídá {METADATA} "
            f"version={nova_verze}")

    if nalezy:
        print("Nálezy:")
        for nalez in nalezy:
            print(f"  {nalez}")
        return 1
    print(f"Kontrola verze a changelogu: v{stara_verze} -> v{nova_verze}, "
          f"bez nálezů")
    return 0


if __name__ == "__main__":
    sys.exit(main())
