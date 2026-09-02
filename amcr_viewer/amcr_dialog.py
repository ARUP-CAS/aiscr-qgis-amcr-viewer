# -*- coding: utf-8 -*-
from qgis.core import (
    Qgis,
    QgsApplication,
    QgsAuthMethodConfig,
    QgsMessageLog,
    QgsTask,
)
from qgis.gui import QgsDateEdit
from qgis.PyQt.QtCore import QSettings, Qt
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from qgis.utils import iface

from .amcr_codelists import (
    AREAL,
    DRUH_LOKALITY,
    DRUH_NALEZU,
    JISTOTA,
    KATASTRY,
    KRAJE,
    LOKALITA_ZACHOVALOST,
    NALEZ_KATEGORIE,
    NALEZCE,
    NALEZOVE_OKOLNOSTI,
    OBDOBI,
    OKRESY,
    ORGANIZACE,
    PIAN_PRESNOST,
    PRISTUPNOST,
    SPECIFIKACE,
    TYP_AKCE,
    TYP_LOKALITY,
    VEDOUCI,
    download_heslare,
    refresh_globals,
)

# The date filter of the API requires both bounds; a one-sided range makes
# the server fail with an ArrayIndexOutOfBoundsException and '*' is not
# accepted either. An empty picker is therefore replaced by these sentinels,
# which are also the default limits of QgsDateEdit.
DATE_OPEN_FROM = "0001-01-01"
DATE_OPEN_TO = "9999-12-31"

# Shown by a date picker that is left empty
DATE_NULL_TEXT = "neomezeno"


# Keep Python references to running tasks. QgsTaskManager only holds the
# C++ object; without a Python-side reference the wrapper can be garbage
# collected before the task finishes, which crashes QGIS.
_ACTIVE_TASKS = []


class UpdateCodelistsTask(QgsTask):
    def __init__(self, description):
        super().__init__(description, QgsTask.Flag.CanCancel)
        self.success = False
        self.exception = None

    def run(self):
        """Runs in a background thread."""
        try:
            # Call the download function with the task reference
            self.success = download_heslare(task=self)
            return self.success
        except Exception as e:
            self.exception = e
            return False

    def finished(self, result):
        """Runs in the main thread after run() completes."""
        if result:
            # Safely update the global variables in the main thread
            refresh_globals()
            QgsMessageLog.logMessage(
                "Hesláře AMČR byly úspěšně aktualizovány.",
                "AMČR", Qgis.MessageLevel.Info
            )
        else:
            if self.isCanceled():
                QgsMessageLog.logMessage(
                    "Aktualizace heslářů byla zrušena.",
                    "AMČR", Qgis.MessageLevel.Warning
                )
            else:
                QgsMessageLog.logMessage(
                    f"Chyba aktualizace: {self.exception}",
                    "AMČR", Qgis.MessageLevel.Critical
                )


class FilterableSelectionDialog(QDialog):
    """
    A custom dialog for selecting multiple items from
    a list with a search filter.
    Updated for PyQt6/Qt6 compatibility.
    """
    def __init__(self, title, data_dict, preselected_codes, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Výběr: {title}")
        self.resize(400, 500)

        # Store the source data and previously selected items
        self.data_dict = data_dict
        self.preselected = preselected_codes if preselected_codes else []

        layout = QVBoxLayout()

        # Setup search input for filtering items
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Hledat v seznamu...")
        self.search_bar.textChanged.connect(self.filter_list)
        layout.addWidget(self.search_bar)

        # Main list widget for displaying selectable items
        self.list_widget = QListWidget()
        self.populate_list()
        layout.addWidget(self.list_widget)

        # Standard OK/Cancel dialog buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setLayout(layout)

    def populate_list(self):
        # Sort items alphabetically by their display name
        sorted_names = sorted(self.data_dict.keys())
        for name in sorted_names:
            code = self.data_dict[name]
            item = QListWidgetItem(name)

            # Store the actual code (ID) hidden in the UserRole
            item.setData(Qt.ItemDataRole.UserRole, code)

            # Make the item checkable (adds a checkbox)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)

            # Restore previous selection state
            if code in self.preselected:
                item.setCheckState(Qt.CheckState.Checked)
            else:
                item.setCheckState(Qt.CheckState.Unchecked)

            self.list_widget.addItem(item)

    def filter_list(self, text):
        # Hide items that don't match the search text (case-insensitive)
        search_text = text.lower()
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            item.setHidden(search_text not in item.text().lower())

    def get_selected_codes(self):
        """Returns the hidden codes and display labels of all checked items."""
        codes = []
        labels = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                codes.append(item.data(Qt.ItemDataRole.UserRole))
                labels.append(item.text())
        return codes, labels


# --- Main window ---
class AmcrFilterDialog(QDialog):
    """
    The main filtering UI where users set criteria before downloading data.
    """
    def __init__(self, typ_dat, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Filtr AMČR")
        self.resize(500, 750)

        # Determines if we are fetching 'akce' (events)
        # or 'lokalita' (sites)
        self.typ_dat = typ_dat

        # Cache dictionary to store selected codes for each category
        self.selection_cache = {
            'organizace': [],
            'kraj': [],
            'obdobi': [],
            'areal': [],
            'typ_akce': [],
            'okres': [],
            'katastr': [],
            'vedouci': [],
            'pian_presnost': [],
            'pristupnost': [],
            'typ_lokality': [],
            'druh_lokality': [],
            'jistota': [],
            'lokalita_zachovalost': [],
            'nalez_kategorie': [],
            'druh_nalezu': [],
            'specifikace': [],
            'nalezove_okolnosti': [],
            'nalezce': [],
        }

        # Date range pickers, filled by setup_date_range():
        # (API field, label for messages, 'from' widget, 'to' widget)
        self.date_ranges = []

        layout = QVBoxLayout()

        # Filter by current map canvas extent
        self.chk_bbox = QCheckBox("Omezit vyhledávání rozsahem okna")
        self.chk_bbox.setChecked(True)
        layout.addWidget(self.chk_bbox)

        # Positive/negative evidence – valid for Akce

        if self.typ_dat == "akce":
            self.chk_posevidence = QCheckBox("Pouze pozitivní zjištění")
            layout.addWidget(self.chk_posevidence)
            self.chk_proj_akce = QCheckBox("Pouze projektové akce")
            layout.addWidget(self.chk_proj_akce)

        layout.addSpacing(10)

        # Spatial information – valid for all

        self.picker_kraj = self.setup_picker("Kraj", 'kraj', KRAJE)
        layout.addWidget(self.picker_kraj)

        self.picker_okres = self.setup_picker("Okres", 'okres', OKRESY)
        layout.addWidget(self.picker_okres)

        self.picker_katastr = self.setup_picker(
            "Katastr",
            'katastr',
            KATASTRY
        )
        layout.addWidget(self.picker_katastr)

        self.picker_pristupnost = self.setup_picker(
            "Přístupnost",
            'pristupnost',
            PRISTUPNOST
        )
        layout.addWidget(self.picker_pristupnost)

        # Filters valid for Akce

        if self.typ_dat in ["lokalita", "akce"]:
            self.picker_presnost = self.setup_picker(
                "PIAN – přesnost",
                'pian_presnost',
                PIAN_PRESNOST
            )
            layout.addWidget(self.picker_presnost)

        if self.typ_dat in ["samostatny_nalez", "akce"]:
            self.picker_org = self.setup_picker(
                "Organizace",
                'organizace',
                ORGANIZACE
            )
            layout.addWidget(self.picker_org)

        if self.typ_dat == "akce":
            self.picker_vedouci = self.setup_picker(
                "Vedoucí výzkumu",
                'vedouci',
                VEDOUCI
            )
            layout.addWidget(self.picker_vedouci)

            # Type of event

            self.picker_typ = self.setup_picker(
                "Typ výzkumu",
                'typ_akce',
                TYP_AKCE
            )
            layout.addWidget(self.picker_typ)

            self.box_datum = self.setup_date_range("Datum", [
                ("akce_datum_zahajeni", "Zahájení", "Datum zahájení"),
                ("akce_datum_ukonceni", "Ukončení", "Datum ukončení"),
            ])
            layout.addWidget(self.box_datum)

        # Filters valid for Lokality

        if self.typ_dat == "lokalita":
            self.picker_typ_lokality = self.setup_picker(
                "Lokalita – typ",
                'typ_lokality',
                TYP_LOKALITY
            )
            layout.addWidget(self.picker_typ_lokality)

            self.picker_druh_lokality = self.setup_picker(
                "Lokalita – druh",
                'druh_lokality',
                DRUH_LOKALITY
            )
            layout.addWidget(self.picker_druh_lokality)

            self.picker_jistota = self.setup_picker(
                "Lokalita – jistota určení",
                'jistota',
                JISTOTA
            )
            layout.addWidget(self.picker_jistota)

            self.picker_lokalita_zachovalost = self.setup_picker(
                "Lokalita – stav dochování",
                'lokalita_zachovalost',
                LOKALITA_ZACHOVALOST
            )
            layout.addWidget(self.picker_lokalita_zachovalost)

        # Contextual information

        self.picker_obdobi = self.setup_picker("Období", 'obdobi', OBDOBI)
        layout.addWidget(self.picker_obdobi)

        if self.typ_dat == "samostatny_nalez":
            self.picker_nalez_kategorie = self.setup_picker(
                "Kategorie nálezu",
                'nalez_kategorie',
                NALEZ_KATEGORIE
            )
            layout.addWidget(self.picker_nalez_kategorie)

            self.picker_druh_nalezu = self.setup_picker(
                "Druh nálezu",
                'druh_nalezu',
                DRUH_NALEZU
            )
            layout.addWidget(self.picker_druh_nalezu)

            self.picker_specifikace = self.setup_picker(
                "Materiál",
                'specifikace',
                SPECIFIKACE
            )
            layout.addWidget(self.picker_specifikace)

            self.picker_nalezove_okolnosti = self.setup_picker(
                "Okolnosti nálezu",
                'nalezove_okolnosti',
                NALEZOVE_OKOLNOSTI
            )
            layout.addWidget(self.picker_nalezove_okolnosti)

            self.picker_nalezce = self.setup_picker(
                "Nálezce",
                'nalezce',
                NALEZCE
            )
            layout.addWidget(self.picker_nalezce)

            # Lokalita has no date field in the index at all, so the block
            # is built only for the two entities that do
            self.box_datum = self.setup_date_range("Datum nálezu", [
                ("samostatny_nalez_datum_nalezu", "", "Datum nálezu"),
            ])
            layout.addWidget(self.box_datum)

        if self.typ_dat != "samostatny_nalez":
            self.picker_areal = self.setup_picker("Areál", 'areal', AREAL)
            layout.addWidget(self.picker_areal)

            # Option to download related components table
            self.chk_komponenty = QCheckBox("Načíst komponenty")
            layout.addWidget(self.chk_komponenty)

        # Warning label
        self.lbl_komponenty_warning = QLabel(
            "⚠ Při načtení komponent jsou prostorové prvky duplikovány — "
            "každý prvek odpovídá jedné komponentě. "
            "Prostorové analýzy (plochy, počty) mohou být zkreslené."
        )
        self.lbl_komponenty_warning.setWordWrap(True)
        self.lbl_komponenty_warning.setStyleSheet(
            "color: #8a6d00; background-color: #fff8e1; "
            "border: 1px solid #ffe082; border-radius: 4px; padding: 6px;"
        )
        self.lbl_komponenty_warning.setVisible(False)
        layout.addWidget(self.lbl_komponenty_warning)

        if self.typ_dat != "samostatny_nalez":
            self.chk_komponenty.toggled.connect(
                self.lbl_komponenty_warning.setVisible
            )

        # Pushes everything above to the top
        layout.addStretch(1)

        # The filter stack is taller than the window on every entity
        # (over 1000 px for 'akce'), so it scrolls. The buttons stay
        # outside the scroll area, otherwise the user would have to
        # scroll to the bottom just to confirm the dialog.
        content = QWidget()
        content.setLayout(layout)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(content)

        outer = QVBoxLayout()
        outer.addWidget(scroll)

        # Main dialog OK/Cancel/Update buttons

        buttons = QDialogButtonBox()

        self.btn_update = QPushButton("Aktualizovat hesláře 🔄")
        self.btn_update.setToolTip(
            "Provede kompletní aktualizaci heslářů AMČR. "
            "Toto bude trvat pár minut."
        )
        self.btn_update.clicked.connect(self.action_update_heslare)

        buttons.addButton(
            self.btn_update,
            QDialogButtonBox.ButtonRole.ActionRole
        )
        buttons.addButton(QDialogButtonBox.StandardButton.Ok)
        buttons.addButton(QDialogButtonBox.StandardButton.Cancel)

        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        self.setLayout(outer)

    def setup_picker(self, label_text, cache_key, data_source, extra_btn=None):
        """
        Creates a reusable UI component consisting of a label, a read-only
        text field showing selected items, and a button to open
        the selection dialog.
        """
        row_widget = QGroupBox(label_text)
        row_layout = QHBoxLayout()
        row_layout.setContentsMargins(5, 5, 5, 5)

        # Read-only field displaying the names of selected items
        display_field = QLineEdit()
        display_field.setReadOnly(True)
        display_field.setPlaceholderText("Nic nevybráno (vše)")
        display_field.setStyleSheet("background-color: #f0f0f0; color: #333;")

        btn = QPushButton("Vybrat...")
        btn.setFixedWidth(80)

        # Nested handler: opens the selection dialog and saves the result
        def open_dialog():
            dlg = FilterableSelectionDialog(
                label_text,
                data_source,
                self.selection_cache[cache_key],
                self
            )
            if dlg.exec() == QDialog.DialogCode.Accepted:
                codes, labels = dlg.get_selected_codes()
                # Update the local cache with selected IDs
                self.selection_cache[cache_key] = codes
                # Update the display field with the selected item names
                if labels:
                    display_field.setText(", ".join(labels))
                else:
                    display_field.clear()

        # Special case: pre-select default PIAN accuracy levels
        if cache_key == 'pian_presnost':
            display_field.setText(
                "odchylka jednotky metrů, odchylka desítky metrů, "
                "odchylka stovky metrů"
            )
            self.selection_cache[cache_key] = [
                'HES-000861',
                'HES-000862',
                'HES-000863',
            ]

        btn.clicked.connect(open_dialog)

        row_layout.addWidget(display_field)
        row_layout.addWidget(btn)

        # Optionally append an extra button (e.g. a refresh button)
        if extra_btn:
            row_layout.addWidget(extra_btn)

        row_widget.setLayout(row_layout)
        return row_widget

    def setup_date_range(self, title, rows):
        """
        Creates a compact date range block: one row per API date field,
        each with a 'from' and a 'to' picker.

        rows is a list of (api_field, row_label, name_for_messages).
        An empty row_label is used when the group box title already names
        the field, which keeps the single-row variant from repeating itself.

        A picker left empty means an open bound; the sentinel is
        substituted in get_filters(), not here, so that an untouched
        block adds no filter at all.
        """
        row_widget = QGroupBox(title)
        grid = QGridLayout()
        grid.setContentsMargins(5, 5, 5, 5)
        grid.setVerticalSpacing(3)
        grid.setHorizontalSpacing(6)

        for row, (api_field, row_label, name) in enumerate(rows):
            if row_label:
                grid.addWidget(QLabel(row_label), row, 0)

            date_from = self._date_edit(
                f"{name} – od (prázdné = bez dolní meze)"
            )
            date_to = self._date_edit(
                f"{name} – do (prázdné = bez horní meze)"
            )

            separator = QLabel("–")
            separator.setAlignment(Qt.AlignmentFlag.AlignCenter)

            grid.addWidget(date_from, row, 1)
            grid.addWidget(separator, row, 2)
            grid.addWidget(date_to, row, 3)

            self.date_ranges.append((api_field, name, date_from, date_to))

        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)

        row_widget.setLayout(grid)
        return row_widget

    @staticmethod
    def _date_edit(tooltip):
        """
        A date picker that may stay empty.

        clear() is essential here – setEmpty() looks empty but leaves
        isNull() False with today's date, which would silently apply
        a filter the user never set.
        """
        widget = QgsDateEdit()
        widget.setAllowNull(True)
        widget.setNullRepresentation(DATE_NULL_TEXT)
        widget.setDisplayFormat("d. M. yyyy")
        widget.setCalendarPopup(True)
        widget.clear()
        widget.setToolTip(tooltip)
        return widget

    def accept(self):
        """
        Blocks the dialog on a reversed date range. The API answers such
        a query with zero records and no error, which is indistinguishable
        from a genuinely empty result.
        """
        reversed_ranges = [
            name for _, name, date_from, date_to in self.date_ranges
            if not date_from.isNull() and not date_to.isNull()
            and date_from.date() > date_to.date()
        ]

        if reversed_ranges:
            QMessageBox.warning(
                self,
                "Neplatné rozmezí",
                "U těchto filtrů je počáteční datum novější než koncové:\n"
                + "\n".join(f"• {name}" for name in reversed_ranges)
                + "\n\nDotaz by nevrátil žádný záznam. Opravte rozmezí, "
                "nebo jedno z polí vyprázdněte."
            )
            return

        super().accept()

    def action_update_heslare(self):
        # Create the task instance and keep a reference so the Python
        # wrapper survives until the task finishes
        task = UpdateCodelistsTask("Aktualizace heslářů AMČR")
        _ACTIVE_TASKS.append(task)

        # Prevent parallel downloads overwriting heslar.csv
        self.btn_update.setEnabled(False)

        # Message boxes are parented to the main window, not to this dialog –
        # the dialog may already be closed (and its C++ object deleted)
        # by the time the minute-long task finishes.
        parent_win = iface.mainWindow() if iface else None

        def _cleanup():
            if task in _ACTIVE_TASKS:
                _ACTIVE_TASKS.remove(task)
            try:
                self.btn_update.setEnabled(True)
            except RuntimeError:
                pass  # dialog already closed

        def on_completed():
            _cleanup()
            QMessageBox.information(
                parent_win,
                "Hotovo",
                "Hesláře byly úspěšně aktualizovány."
            )

        # Show the exact error if the task fails
        def on_error():
            _cleanup()
            if task.exception:
                # This will show exactly what went wrong (e.g. PermissionError)
                msg = (
                    "Aktualizace selhala z důvodu chyby:\n"
                    f"{task.exception!s}"
                )
            else:
                msg = "Aktualizace byla zrušena uživatelem."
            QMessageBox.warning(parent_win, "Chyba / Zrušeno", msg)

        task.taskCompleted.connect(on_completed)
        task.taskTerminated.connect(on_error)

        QgsApplication.taskManager().addTask(task)

    def get_bbox(self):
        return "true" if self.chk_bbox.isChecked() else "false"

    def get_komponenty(self):
        if self.typ_dat in ["akce", "lokalita"]:
            return "true" if self.chk_komponenty.isChecked() else "false"
        return "false"

    def get_filters(self):
        """Compiles the user selections from the cache into
        API-ready filter parameters."""
        filters = {}

        if self.selection_cache['kraj']:
            filters['f_kraj'] = self.selection_cache['kraj']
        if self.selection_cache['okres']:
            filters['f_okres'] = self.selection_cache['okres']
        if self.selection_cache['katastr']:
            filters['f_katastr'] = self.selection_cache['katastr']
        if self.selection_cache['obdobi']:
            filters['f_obdobi'] = self.selection_cache['obdobi']
        if self.selection_cache['areal']:
            filters['f_areal'] = self.selection_cache['areal']
        if self.selection_cache['pian_presnost']:
            filters['f_pian_presnost'] = self.selection_cache['pian_presnost']
        if self.selection_cache['pristupnost']:
            filters['pristupnost'] = self.selection_cache['pristupnost']

        if self.typ_dat == "akce":
            if self.chk_posevidence.isChecked():
                filters['posevidence'] = 'true'
            if self.chk_proj_akce.isChecked():
                filters['proj_akce'] = 'true'

        if self.selection_cache['typ_akce']:
            filters['f_typ_vyzkumu'] = self.selection_cache['typ_akce']
        if self.selection_cache['vedouci']:
            filters['f_vedouci'] = self.selection_cache['vedouci']

        if self.selection_cache['organizace']:
            filters['f_organizace'] = self.selection_cache['organizace']

        if self.selection_cache['typ_lokality']:
            filters['f_typ_lokality'] = self.selection_cache['typ_lokality']
        if self.selection_cache['druh_lokality']:
            filters['f_druh_lokality'] = self.selection_cache['druh_lokality']
        if self.selection_cache['jistota']:
            filters['f_jistota'] = self.selection_cache['jistota']
        if self.selection_cache['lokalita_zachovalost']:
            filters['f_lokalita_zachovalost'] = (
                self.selection_cache['lokalita_zachovalost']
            )

        # Samostatné nálezy
        if self.selection_cache['nalez_kategorie']:
            filters['f_kategorie'] = self.selection_cache['nalez_kategorie']
        if self.selection_cache['druh_nalezu']:
            filters['f_druh_nalezu'] = self.selection_cache['druh_nalezu']
        if self.selection_cache['specifikace']:
            filters['f_specifikace'] = self.selection_cache['specifikace']
        if self.selection_cache['nalezove_okolnosti']:
            filters['f_nalezove_okolnosti'] = (
                self.selection_cache['nalezove_okolnosti']
            )
        if self.selection_cache['nalezce']:
            filters['f_nalezce'] = self.selection_cache['nalezce']

        # Date ranges – the API needs both bounds, so an empty picker is
        # replaced by a sentinel. A block with both pickers empty adds no
        # filter at all; sending the full 0001–9999 range would only
        # clutter the log without narrowing anything.
        for api_field, _, date_from, date_to in self.date_ranges:
            if date_from.isNull() and date_to.isNull():
                continue

            od = (DATE_OPEN_FROM if date_from.isNull()
                  else date_from.date().toString("yyyy-MM-dd"))
            do = (DATE_OPEN_TO if date_to.isNull()
                  else date_to.date().toString("yyyy-MM-dd"))

            filters[api_field] = f"{od},{do}"

        return filters


class LoginDialog(QDialog):
    """
    Dialog for saving AMČR login credentials securely in the
    QGIS Authentication Manager.

    Credentials are encrypted by the platform's native secret storage
    (DPAPI on Windows, Keychain on macOS, encrypted SQLite on Linux).
    The auth config ID is persisted in QSettings so the session can be
    restored automatically after a QGIS restart.

    Note on QgsAuthManager quirks (QGIS 4 / Python bindings):
    - hasConfigId() is unreliable – it checks an in-memory cache that may not
      be populated yet. We never use it as a hard gate; we skip it and call
      loadAuthenticationConfig() directly instead.
    - storeAuthenticationConfig() and loadAuthenticationConfig() both have
      SIP_INOUT on their config parameter, so Python bindings return a tuple
      (bool, QgsAuthMethodConfig) rather than just bool. Always unpack both.
    - loadAuthenticationConfig() with full=False loads only metadata
      (name, method,
      id) but NOT the config() values like username/password. Use full=True to
      access those.
    """

    SETTINGS_KEY = "amcr_viewer/auth_config_id"
    CONFIG_NAME = "AMČR Viewer"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Přihlášení do AMČR")
        self.setMinimumWidth(360)

        layout = QVBoxLayout()

        # Check whether a config ID is already stored from a previous session.
        # We attempt a lightweight load (full=False) to confirm it is readable,
        # since hasConfigId() may return False even for valid configs
        # (cache lag).
        # The Auth Manager must be unlocked before we attempt to read from it;
        # otherwise loadAuthenticationConfig() returns ok=False even for valid
        # configs, causing _has_saved to be incorrectly set to False.
        existing_id = QSettings().value(self.SETTINGS_KEY, "")
        if existing_id:
            QgsApplication.authManager().setMasterPassword(True)
        username = self._load_username_from_config(existing_id)
        self._has_saved = bool(existing_id) and bool(username)

        if self._has_saved:
            info = QLabel(
                "✔ Přihlašovací údaje jsou bezpečně uloženy "
                "ve správci autentizace QGIS.\n"
                "Vyplňte pole níže pouze pokud je chcete změnit."
            )
            info.setStyleSheet("color: green; font-style: italic;")
        else:
            info = QLabel(
                "Zadejte přihlašovací údaje k Digitálnímu archivu AMČR.\n"
                "Budou zašifrovaně uloženy ve správci autentizace QGIS."
            )
        info.setWordWrap(True)
        layout.addWidget(info)
        layout.addSpacing(8)

        form = QFormLayout()

        self.txt_user = QLineEdit()
        self.txt_user.setPlaceholderText("např. jan.novak@email.cz")
        # Pre-fill the stored username (not sensitive) for convenience
        if self._has_saved:
            self.txt_user.setText(self._load_username_from_config(existing_id))
        form.addRow("E-mail:", self.txt_user)

        self.txt_pass = QLineEdit()
        self.txt_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_pass.setPlaceholderText(
            "ponechte prázdné pro zachování stávajícího hesla"
            if self._has_saved
            else "heslo"
        )
        form.addRow("Heslo:", self.txt_pass)

        layout.addLayout(form)
        layout.addSpacing(8)

        if self._has_saved:
            btn_forget = QPushButton("Odebrat uložené přihlašovací údaje")
            btn_forget.setStyleSheet("color: #c0392b;")
            btn_forget.clicked.connect(self._forget_credentials)
            layout.addWidget(btn_forget)

        layout.addStretch(1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setLayout(layout)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load_config(config_id: str, full: bool = False):
        """
        Attempt to load a QgsAuthMethodConfig by ID.
        Returns (ok, cfg). Never raises; returns (False, empty cfg)
        on any error.
        full=True decrypts and includes the password.
        """
        try:
            auth_mgr = QgsApplication.authManager()
            cfg = QgsAuthMethodConfig()
            result = auth_mgr.loadAuthenticationConfig(config_id, cfg, full)
            # Python bindings return (bool, cfg) due to SIP_INOUT parameter
            if isinstance(result, tuple):
                return result
            return result, cfg
        except Exception:
            return False, QgsAuthMethodConfig()

    def _load_username_from_config(self, config_id: str) -> str:
        """Load the username from a stored config.
        Requires full=True since config() values are only populated
        when the config is fully decrypted."""
        ok, cfg = self._load_config(config_id, full=True)
        return cfg.config("username", "") if ok else ""

    def _ensure_master_password(self) -> bool:
        """
        Ensure the Auth Manager is unlocked before writing.
        Prompts the user to set or enter the master password if needed.
        Returns True if the manager is ready, False if the user cancelled.
        """
        auth_mgr = QgsApplication.authManager()

        if auth_mgr.isDisabled():
            QMessageBox.critical(
                self, "Správce autentizace nedostupný",
                "Správce autentizace QGIS je zakázán nebo poškozený.\n"
                "Zkuste obnovit databázi: "
                "Nastavení → Možnosti → Autentizace → Pomůcky."
            )
            return False

        # setMasterPassword(True) shows the QGIS
        # master password dialog if needed
        if not auth_mgr.setMasterPassword(True):
            return False  # User cancelled the master password dialog

        return True

    def _verify_credentials(self, username: str, password: str) -> bool:
        """
        Verify the credentials against the API before saving them.
        Returns True if they should be stored: either the login succeeded,
        or the server was unreachable and the user chose to keep them
        unverified. Wrong credentials are never stored.
        """
        # Lazy import to avoid an import cycle
        # (amcr_tools imports LoginDialog lazily as well)
        from . import amcr_tools

        if amcr_tools.login_to_api(username, password):
            return True

        if amcr_tools.LAST_LOGIN_ERROR == 'network':
            answer = QMessageBox.question(
                self,
                "Server nedostupný",
                "Přihlašovací údaje se nepodařilo ověřit – server AMČR "
                "je nedostupný.\nChcete je přesto uložit (neověřené)?",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No
            )
            return answer == QMessageBox.StandardButton.Yes

        QMessageBox.warning(
            self,
            "Neplatné přihlašovací údaje",
            "Přihlášení se nezdařilo – zkontrolujte e-mail a heslo.\n"
            "Údaje nebyly uloženy."
        )
        return False

    # ------------------------------------------------------------------
    # Button actions
    # ------------------------------------------------------------------

    def _save_and_accept(self):
        username = self.txt_user.text().strip()
        password = self.txt_pass.text()

        if not username:
            QMessageBox.warning(
                self,
                "Chybí údaje",
                "Vyplňte prosím e-mailovou adresu."
            )
            return

        existing_id = QSettings().value(self.SETTINGS_KEY, "")
        auth_mgr = QgsApplication.authManager()

        # If a config already exists and the password field is blank,
        # update only the username and keep the existing encrypted password.
        if not password and existing_id:
            ok, cfg = self._load_config(existing_id, full=True)
            if ok:
                if not self._ensure_master_password():
                    return
                # Verify the new username against the stored password
                if not self._verify_credentials(
                    username, cfg.config("password", "")
                ):
                    return
                cfg.setConfig("username", username)
                auth_mgr.updateAuthenticationConfig(cfg)
                self.accept()
                return

        if not password:
            QMessageBox.warning(self, "Chybí údaje", "Vyplňte prosím heslo.")
            return

        # Verify before prompting for the master password – wrong
        # credentials must never reach the Authentication Manager
        if not self._verify_credentials(username, password):
            return

        if not self._ensure_master_password():
            return

        cfg = QgsAuthMethodConfig()
        cfg.setName(self.CONFIG_NAME)
        cfg.setMethod("Basic")
        cfg.setConfig("username", username)
        cfg.setConfig("password", password)  # nosec B106

        settings = QSettings()

        # Try to update an existing config first;
        # fall back to creating a new one.
        # We skip hasConfigId() as it may return False
        # despite the config existing
        # (in-memory cache may not be populated yet in QGIS 4).
        ok_load, _ = (
            self._load_config(existing_id, full=False)
            if existing_id
            else (False, None)
        )
        if ok_load:
            cfg.setId(existing_id)
            ok = auth_mgr.updateAuthenticationConfig(cfg)
        else:
            ok, cfg = auth_mgr.storeAuthenticationConfig(cfg)

        config_id = cfg.id() if cfg else ""

        if not ok or not config_id:
            QMessageBox.critical(
                self, "Chyba uložení",
                "Přihlašovací údaje se nepodařilo "
                "uložit do správce autentizace QGIS.\n"
                "Zkuste restartovat QGIS a přihlásit se znovu."
            )
            return

        settings.setValue(self.SETTINGS_KEY, config_id)
        self.accept()

    def _forget_credentials(self):
        settings = QSettings()
        existing_id = settings.value(self.SETTINGS_KEY, "")
        if existing_id:
            QgsApplication.authManager().removeAuthenticationConfig(
                existing_id
            )
            settings.remove(self.SETTINGS_KEY)
        QMessageBox.information(
            self,
            "Hotovo",
            "Uložené přihlašovací údaje byly odebrány."
        )
        self.reject()

    # ------------------------------------------------------------------
    # Public static API – call this anywhere in the plugin to get credentials
    # ------------------------------------------------------------------

    @staticmethod
    def get_credentials() -> tuple[str, str]:
        """
        Retrieve (username, password) from the QGIS Authentication Manager.
        Returns ('', '') if no credentials are stored or the manager is locked.

        Note: hasConfigId() is intentionally skipped here – it checks an
        in-memory cache that may lag behind the actual database contents,
        causing false negatives (see class docstring).
        loadAuthenticationConfig() is called directly and its return value is
        used as the authoritative result.
        """
        settings = QSettings()
        config_id = settings.value(LoginDialog.SETTINGS_KEY, "")

        if not config_id:
            return "", ""

        ok, cfg = LoginDialog._load_config(config_id, full=True)
        if not ok:
            return "", ""

        return (cfg.config("username", ""),
                cfg.config("password", ""))  # nosec B106
