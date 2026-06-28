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

## Verzování a release

- Verze pluginu žije v **`amcr_viewer/metadata.txt`** (`version=`).
- **Při každé změně chování / nové funkci** povyš verzi a doplň položku do
  `changelog=` v `metadata.txt` (formát `vX.Y.Z (RRRR-MM-DD)` + odrážky).
- Datum v changelogu ber z **deterministického zdroje**, ne z paměti, např.
  `python -c "import datetime; print(datetime.date.today().isoformat())"`.
- Release se vytváří publikací GitHub Release; workflow
  `.github/workflows/release_plugin.yml` zabalí složku `amcr_viewer/` do
  `amcr_viewer.zip` a přiloží ji k releasu. Do ZIPu se nesmí dostat `.git*`
  soubory.

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
QGIS). Automatizované testy zatím repozitář neobsahuje – změny ověřuj ručně
v QGIS na podporované verzi.
