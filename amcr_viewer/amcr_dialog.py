# -*- coding: utf-8 -*-
from qgis.PyQt.QtWidgets import (QDialog, QVBoxLayout,
                                 QLineEdit, QDialogButtonBox,
                                 QCheckBox, QGroupBox, QPushButton,
                                 QListWidget, QListWidgetItem, QHBoxLayout,
                                 QMessageBox, QLabel, QFormLayout)
from qgis.PyQt.QtCore import Qt, QSettings
from qgis.core import (QgsTask, QgsApplication,
                       QgsMessageLog, Qgis, QgsAuthMethodConfig)
from .amcr_codelists import (OBDOBI, TYP_AKCE, KRAJE, AREAL, ORGANIZACE,
                             OKRESY, KATASTRY, VEDOUCI, PIAN_PRESNOST,
                             TYP_LOKALITY, DRUH_LOKALITY, JISTOTA,
                             LOKALITA_ZACHOVALOST, PRISTUPNOST,
                             download_heslare, refresh_globals)


class UpdateCodelistsTask(QgsTask):
    def __init__(self, description):
        super().__init__(description, QgsTask.CanCancel)
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
                "AMČR", Qgis.Info)
        else:
            if self.isCanceled():
                QgsMessageLog.logMessage(
                    "Aktualizace heslářů byla zrušena.",
                    "AMČR", Qgis.Warning)
            else:
                QgsMessageLog.logMessage(
                    f"Chyba aktualizace: {self.exception}",
                    "AMČR", Qgis.Critical)


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
            'organizace': [], 'kraj': [], 'obdobi': [], 'areal': [],
            'typ_akce': [], 'okres': [], 'katastr': [], 'vedouci': [],
            'pian_presnost': [], 'pristupnost': [], 'typ_lokality': [],
            'druh_lokality': [], 'jistota': [], 'lokalita_zachovalost': []
        }

        layout = QVBoxLayout()

        # Filter by current map canvas extent
        self.chk_bbox = QCheckBox("Omezit vyhledávání rozsahem okna")
        self.chk_bbox.setChecked(True)
        layout.addWidget(self.chk_bbox)

        # Positive/negative evidence – valid for Akce

        if self.typ_dat == "akce":
            self.chk_posevidence = QCheckBox("Pouze pozitivní zjištění")
            layout.addWidget(self.chk_posevidence)

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

        self.picker_presnost = self.setup_picker(
            "PIAN – přesnost",
            'pian_presnost',
            PIAN_PRESNOST
        )
        layout.addWidget(self.picker_presnost)

        self.picker_pristupnost = self.setup_picker(
            "Přístupnost",
            'pristupnost',
            PRISTUPNOST
        )
        layout.addWidget(self.picker_pristupnost)

        # Filters valid for Akce

        if self.typ_dat == "akce":
            self.picker_org = self.setup_picker(
                "Organizace",
                'organizace',
                ORGANIZACE
            )
            layout.addWidget(self.picker_org)

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
                "Lokalita - stav dochování",
                'lokalita_zachovalost',
                LOKALITA_ZACHOVALOST
            )
            layout.addWidget(self.picker_lokalita_zachovalost)

        # Contextual information

        self.picker_obdobi = self.setup_picker("Období", 'obdobi', OBDOBI)
        layout.addWidget(self.picker_obdobi)

        self.picker_areal = self.setup_picker("Areál", 'areal', AREAL)
        layout.addWidget(self.picker_areal)

        # Option to download related components table
        self.chk_komponenty = QCheckBox("Načíst komponenty")
        layout.addWidget(self.chk_komponenty)

        # Pushes everything above to the top
        layout.addStretch(1)

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
        layout.addWidget(buttons)

        self.setLayout(layout)

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
                'HES-000863'
            ]

        btn.clicked.connect(open_dialog)

        row_layout.addWidget(display_field)
        row_layout.addWidget(btn)

        # Optionally append an extra button (e.g. a refresh button)
        if extra_btn:
            row_layout.addWidget(extra_btn)

        row_widget.setLayout(row_layout)
        return row_widget

    def action_update_heslare(self):
        # Create the task instance
        task = UpdateCodelistsTask("Aktualizace heslářů AMČR")

        # Re-enable the button regardless of the outcome
        task.taskCompleted.connect(lambda: self.btn_update.setEnabled(True))
        task.taskTerminated.connect(lambda: self.btn_update.setEnabled(True))

        task.taskCompleted.connect(lambda: QMessageBox.information(
            self,
            "Hotovo",
            "Hesláře byly úspěšně aktualizovány."
        ))

        # Show the exact error if the task fails
        def on_error():
            if task.exception:
                # This will show exactly what went wrong (e.g. PermissionError)
                msg = (
                    "Aktualizace selhala z důvodu chyby:\n"
                    f"{str(task.exception)}"
                )
            else:
                msg = "Aktualizace byla zrušena uživatelem."
            QMessageBox.warning(self, "Chyba / Zrušeno", msg)

        task.taskTerminated.connect(on_error)

        QgsApplication.taskManager().addTask(task)

    def get_bbox(self):
        return "true" if self.chk_bbox.isChecked() else "false"

    def get_komponenty(self):
        return "true" if self.chk_komponenty.isChecked() else "false"

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
            if self.selection_cache['organizace']:
                filters['f_organizace'] = self.selection_cache['organizace']
            if self.selection_cache['typ_akce']:
                filters['f_typ_vyzkumu'] = self.selection_cache['typ_akce']
            if self.selection_cache['vedouci']:
                filters['f_vedouci'] = self.selection_cache['vedouci']

        if self.typ_dat == "lokalita":
            if self.selection_cache['typ_lokality']:
                filters['f_typ_lokality'] = self.selection_cache['typ_lokality']
            if self.selection_cache['druh_lokality']:
                filters['f_druh_lokality'] = self.selection_cache['druh_lokality']
            if self.selection_cache['jistota']:
                filters['f_jistota'] = self.selection_cache['jistota']
            if self.selection_cache['lokalita_zachovalost']:
                filters['f_lokalita_zachovalost'] = self.selection_cache['lokalita_zachovalost']

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
    - loadAuthenticationConfig() with full=False loads only metadata (name, method,
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
                cfg.setConfig("username", username)
                auth_mgr.updateAuthenticationConfig(cfg)
                self.accept()
                return

        if not password:
            QMessageBox.warning(self, "Chybí údaje", "Vyplňte prosím heslo.")
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
        ok_load, existing_cfg = (
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
            QgsApplication.authManager().removeAuthenticationConfig(existing_id)
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

        return cfg.config("username", ""), cfg.config("password", "")  # nosec B106
