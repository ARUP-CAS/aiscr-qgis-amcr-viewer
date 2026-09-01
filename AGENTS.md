# AGENTS.md

Pokyny pro AI agenty i lidské přispěvatele pracující v tomto repozitáři.
Tento soubor je jediný zdroj pravdy; `CLAUDE.md` na něj pouze odkazuje.

## O projektu

**AMČR Viewer** je plugin do QGIS pro stahování a vizualizaci dat z Digitálního
archivu Archeologické mapy ČR (AMČR / AIS CR) – akce (*Fieldwork events*),
lokality (*Sites*) a jejich komponenty. Podporuje anonymní i přihlášený přístup
přes AMČR účet.

Zdroj dat: https://digiarchiv.aiscr.cz/ · Nápověda: https://amcr-help.aiscr.cz/digiarchiv/qgis-viewer.html

## Zařazení v ekosystému AIS CR

Tento repozitář je jedním ze **sourozeneckých repozitářů** ekosystému AIS CR.
Centrální governance a AI konfigurace spravuje hub **`aiscr-management`**; konvence
v tomto souboru jsou s tímto vzorem sladěné a zjednodušené pro potřeby jednoho
QGIS pluginu. Těžkou mašinerii hubu (složka `.agents/`, OpenSpec, sync skripty,
multi-assistant generování) tento repozitář **záměrně nepřebírá**. Při širších
otázkách governance má přednost vzor z `aiscr-management`.

## Struktura repozitáře

```
amcr_viewer/            # vlastní kód pluginu (toto se balí do releasu)
  amcr_viewer.py        # vstupní bod pluginu, integrace do QGIS
  amcr_dialog.py        # dialogy a UI (filtry, přihlášení)
  amcr_tools.py         # stahování dat z API, sestavení vrstev a atributů
  amcr_codelists.py     # hesláře / číselníky (codelists)
  codelists/heslar.csv  # lokální kopie číselníků
  metadata.txt          # metadata pluginu + verze + changelog
  i18n/                 # překlady (.ts)
  *.png                 # ikony
.github/workflows/      # CI – release pluginu
README.md               # uživatelská dokumentace (anglicky)
```

## Konvence

### Jazyk
- **Kód a identifikátory:** anglicky. Atributová pole vrstev musí být ASCII
  kompatibilní (bez diakritiky) – viz historie změn v `metadata.txt`.
- **README a uživatelská dokumentace:** anglicky.
- **Commity, PR a komentáře v issue:** česky.

### Commity
- Styl odpovídá historii: česky, věcně, popisně; jeden commit = jedna logická
  změna.
- První řádek stručně a výstižně (ideálně v imperativu); podrobnosti do těla.
- Pokud je commit připraven s pomocí AI, uveď to v těle commitu nebo v popisu PR.

### Větve
Konvence názvů je sladěná s hubem `aiscr-management`:

- **lidé:** `feat/<téma>` (nová funkce), `fix/<téma>` (oprava), `docs/<téma>`
  (dokumentace), `chore/<téma>` (údržba).
- **AI agenti:** `agents/<jméno-agenta>/<téma>` (např. `agents/claude/oprava-pian`).

Další pravidla:

- Cílová větev pro nový vývoj je aktuální `version/v2.x.y` (ne přímo do
  výchozí větve bez PR).
- **Nikdy** nepushuj přímo do chráněných větví; vždy přes Pull Request.
- Standardizační / nefunkční změny drž v samostatné větvi, ať se nemíchají do
  feature PR.

### Pravidla pro AI agenty (git)
- AI ve výchozím stavu zůstává u **lokální práce na aktuální větvi**.
- Bez **výslovného pokynu** uživatele AI nestageuje (`git add`), necommituje,
  nepushuje ani samo nepřepíná/nezakládá větev pro vzdálené doručení.
- Při výslovném požadavku na push/PR použij větev `agents/<jméno-agenta>/<téma>`;
  pokud aktuální větev tomuto vzoru neodpovídá, vyžádej si nejdřív potvrzení.
- Vytvoření větve, stage, commit, push ani draft PR AI běžně nenabízí; zmiňuj je
  jen tehdy, když jsou pro splnění úkolu opravdu nutné.

### QGIS specifika
- Minimální podporovaná verze QGIS je **3.44** (`qgisMinimumVersion` v
  `metadata.txt`); kód nesmí spoléhat na novější API.
- Vrstvy a atributy se sestavují přes `QgsField` / QGIS API v `amcr_tools.py`.
  Při přidání atributu je potřeba doplnit ho konzistentně na všech místech:
  definice pole (`QgsField`), naplnění hodnoty z dokumentu, překlad hlavičky
  sloupce a export atributů.

### Kompatibilita s Qt6 / QGIS 4

Plugin cílí na QGIS 3.44 i na QGIS 4 (`qgisMaximumVersion=4.99.0`), tedy na
Qt5 i Qt6 zároveň. **Tohle se drží rigorózně** – ne až před releasem, ale při
každé změně kódu. Chování obou větví se liší tiše: pod Qt5 projde i to, co
QGIS 4 odmítne, takže lokální „funguje mi to“ nic nedokazuje.

Závazná pravidla:

- **Nikdy neimportuj přímo z `PyQt5` ani z `PyQt6`.** Vždy přes shim
  `qgis.PyQt.*`. Ten mimo jiné pod Qt6 přetahuje `QAction`, `QActionGroup`
  a `QShortcut` z `QtGui`, takže import z `qgis.PyQt.QtWidgets` je správně.
- **Enumy vždy plně kvalifikované (scoped).** `Qgis.MessageLevel.Info`, ne
  `Qgis.Info`; `QgsTask.Flag.CanCancel`, ne `QgsTask.CanCancel`;
  `QgsWkbTypes.GeometryType.PointGeometry`, ne `QgsWkbTypes.PointGeometry`.
  Totéž pro Qt: `Qt.CheckState.Checked`, `QDialogButtonBox.StandardButton.Ok`.
  Zkrácené tvary sice v QGIS 4.2 zatím fungují, ale oficiální kontrola je
  hlásí a do budoucna mizí.
- **Zdrojové `.py` soubory ukládej bez BOM.** Kontrolní skript čte soubor
  jako UTF-8 bez `utf-8-sig` a na BOM spadne s
  `SyntaxError: invalid non-printable character U+FEFF`, takže se takový
  soubor **vůbec nezkontroluje**. (`codelists/heslar.csv` BOM mít smí, tam je
  kvůli Excelu.)
- Nepoužívej API zrušená v Qt6: `exec_()`, `QRegExp`, `QDesktopWidget`,
  `QApplication.desktop()`, `Qt.MidButton`, `QFontMetrics.width()`,
  `setResizeMode`, atributy `AA_EnableHighDpiScaling` / `AA_UseHighDpiPixmaps`.
- `supportsQt6=True` v `metadata.txt` **nepatří** – bylo zrušeno; o zařazení
  mezi „QGIS 4 Ready“ rozhoduje rozsah `qgisMinimumVersion` až
  `qgisMaximumVersion`.

Ověření před PR, který mění Python kód:

```sh
# oficiální kontrola, kterou pouští i plugins.qgis.org (pyqgis4-checker)
docker run --rm --pull always --user $(id -u):$(id -g) \
  --workdir /workspace/ -v "$(pwd):/workspace/" \
  ghcr.io/qgis/pyqgis4-checker:main-ubuntu \
  pyqt5_to_pyqt6.py --dry_run --logfile /workspace/pyqt6_checker.log .
```

Prázdný log = čisté. Kontrola je na plugins.qgis.org informativní
(neblokuje schválení), ale nález znamená, že plugin v QGIS 4 dříve nebo
později přestane fungovat.

Když je po ruce QGIS 4 (např. flatpak `org.qgis.qgis`), ověř navíc, že se
plugin pod Qt6 opravdu načte:

```sh
flatpak run --command=sh org.qgis.qgis -c \
  'PYTHONPATH=/app/share/qgis/python python3 -c "import qgis.core"'
```

## Verzování a release

- Verze pluginu žije v **`amcr_viewer/metadata.txt`** (`version=`).
- **Při každé změně chování / nové funkci** povyš verzi a doplň položku do
  `changelog=` v `metadata.txt` (formát `vX.Y.Z (RRRR-MM-DD)` + odrážky).
- Datum v changelogu ber z **deterministického zdroje**, ne z paměti, např.
  `python -c "import datetime; print(datetime.date.today().isoformat())"`.
- Release se spouští **pushnutím tagu `vX.Y.Z`**, ne publikací releasu
  v UI. Workflow `.github/workflows/release_plugin.yml` zabalí složku
  `amcr_viewer/` do `amcr_viewer.zip` a založí **koncept** releasu i s touto
  přílohou; text se dopíše a release zveřejní ručně. Do ZIPu se nesmí dostat
  `.git*` soubory.
- Organizace má zapnuté **immutable releases** – k publikovanému releasu už
  nelze nic přiložit. Proto příloha vzniká na konceptu, ještě před
  zveřejněním; workflow spouštěný na `release: published` by vždy selhal.
- Workflow se čte z commitu, na který **tag ukazuje**. Tag proto zakládej až
  na commitu, který obsahuje aktuální podobu workflow – jinak se nespustí nic.

## Pull requesty

- Používej PR šablonu (`.github/pull_request_template.md`): Souhrn / Změny /
  Testování / Kontrolní seznam.
- PR musí mířit do správné `version/v2.x.y` větve.
- Před požádáním o review projdi kontrolní seznam v šabloně (zejména bump verze
  v `metadata.txt`, pokud měníš chování).
- V popisu PR uveď **podíl AI** (např. „text navržen AI, ručně zkontrolováno")
  a odkaz na související issue, pokud existuje.

## Bezpečnost a soukromí

- Do promptů, příkladů ani commitů **nevkládej** ostrá produkční data, plné
  log dumpy ani reálné osobní údaje (PII).
- **Rediguj** secrets, tokeny, API klíče a hesla z čehokoli, co posíláš AI;
  nikdy je necommituj do repozitáře (ani přihlašovací údaje k AMČR účtu).
- Pro interní infrastrukturu (URL, hostname, prostředí) používej placeholdery,
  pokud konkrétní hodnota není nutná a povolená.

## Lokální ověření

Plugin se testuje načtením do QGIS (Plugins → Manage and Install Plugins →
Install from ZIP, nebo nasazením složky `amcr_viewer/` do adresáře pluginů
QGIS). **Ruční test v QGIS nic nenahrazuje** – automatické kontroly ověřují,
že se plugin načte a že projde kontrolami kvality, ne že dělá správnou věc.

### Automatické kontroly

Workflow `.github/workflows/code_quality.yml` pouští při každém PR do `main`
tohle:

| job | co dělá |
|---|---|
| **Lint a bezpečnost** | `check_sources.py`, bandit, detect-secrets, flake8, ruff |
| **Kompatibilita s Qt6** | `pyqgis4-checker` v dockeru |
| **Smoke test** | `smoke_test.py` v `qgis/qgis:ltr` i `qgis/qgis:stable` |
| **Balíček pluginu** | sestaví ZIP, ověří obsah, přiloží jako artefakt |

Smoke test běží v obou podporovaných řadách: `ltr` je QGIS 3.44 na Qt5,
`stable` je QGIS 4.x na Qt6.

Artefakt z posledního jobu se dá stáhnout ze stránky běhu a rovnou
nainstalovat přes *Install from ZIP* – recenzent nemusí nic balit ručně.

Totéž lokálně:

```sh
pip install bandit detect-secrets flake8 ruff

python3 tests/check_sources.py
bandit -r amcr_viewer/
detect-secrets scan --all-files amcr_viewer/
flake8 --config amcr_viewer/.flake8 amcr_viewer/
ruff check .

# smoke test v obou verzích QGIS (docker, bez instalace čehokoli)
for tag in ltr stable; do
  docker run --rm -v "$PWD:/work:ro" -w /work \
    --user "$(id -u):$(id -g)" -e HOME=/tmp \
    "qgis/qgis:$tag" python3 tests/smoke_test.py
done
```

Na co si dát pozor:

- **`pyqgis4-checker` končí kódem 0, i když něco najde** – výsledek je jen
  v logu. Workflow proto kontroluje, že log obsahuje jen hlavičku.
- **`detect-secrets` bez `--all-files` prohledá jen soubory sledované
  gitem** a o nesledovaném souboru mlčí. Vypadá to jako čistý výsledek.
- **Konfigurace lintů je rozdělená schválně.** `amcr_viewer/.flake8` leží
  vedle `metadata.txt`, protože scanner na plugins.qgis.org hledá config
  soubory jen v kořeni balíčku uvnitř ZIPu; díky tomu platí stejná pravidla
  v CI, lokálně i při uploadu. Konfigurace ruffu je naopak v kořenovém
  `pyproject.toml` – ruff se do balíčku pluginu nedistribuuje.
  Viz https://plugins.qgis.org/docs/security-scanning/config-files
- **Verze nástrojů jsou v workflow napevno.** Výchozí sada pravidel ruffu se
  mezi verzemi mění, takže bez pinu by CI začalo padat samo od sebe.
