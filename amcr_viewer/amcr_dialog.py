# -*- coding: utf-8 -*-
from qgis.PyQt.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, 
                                 QLineEdit, QDialogButtonBox, 
                                 QCheckBox, QGroupBox, QPushButton,
                                 QListWidget, QListWidgetItem, QHBoxLayout,
                                 QLabel, QMessageBox, QApplication, QWidget)
from qgis.PyQt.QtCore import Qt
from .amcr_codelists import (OBDOBI, TYP_AKCE, KRAJE, AREAL, ORGANIZACE, 
                             OKRESY, KATASTRY, VEDOUCI, 
                             download_vedouci, refresh_vedouci_cache)

class FilterableSelectionDialog(QDialog):
    def __init__(self, title, data_dict, preselected_codes, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Výběr: {title}")
        self.resize(400, 500)
        self.data_dict = data_dict
        self.preselected = preselected_codes if preselected_codes else []
        layout = QVBoxLayout()
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Hledat v seznamu...")
        self.search_bar.textChanged.connect(self.filter_list)
        layout.addWidget(self.search_bar)
        self.list_widget = QListWidget()
        self.populate_list()
        layout.addWidget(self.list_widget)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.setLayout(layout)

    def populate_list(self):
        sorted_names = sorted(self.data_dict.keys())
        for name in sorted_names:
            code = self.data_dict[name]
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, code)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            if code in self.preselected: item.setCheckState(Qt.Checked)
            else: item.setCheckState(Qt.Unchecked)
            self.list_widget.addItem(item)

    def filter_list(self, text):
        search_text = text.lower()
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if search_text not in item.text().lower(): item.setHidden(True)
            else: item.setHidden(False)

    def get_selected_codes(self):
        codes = []
        labels = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.checkState() == Qt.Checked:
                codes.append(item.data(Qt.UserRole))
                labels.append(item.text())
        return codes, labels


# --- Main window ---
class AmcrFilterDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Filtr AMČR")
        self.resize(500, 750)
        
        # Cache for filtering
        self.selection_cache = {
            'organizace': [], 'kraj': [], 'obdobi': [], 'areal': [], 
            'typ_akce': [], 'okres': [], 'katastr': [], 'vedouci': []
        }
        
        layout = QVBoxLayout()
        
        self.chk_bbox = QCheckBox("Omezit vyhledávání rozsahem okna")
        self.chk_bbox.setChecked(True)
        layout.addWidget(self.chk_bbox)

        self.chk_posevidence = QCheckBox("Pouze pozitivní zjištění")
        layout.addWidget(self.chk_posevidence)
        
        layout.addSpacing(10)

        def setup_picker(label_text, cache_key, data_source, extra_btn=None):
            row_widget = QGroupBox(label_text) 
            # row_widget.setFlat(True)
            
            row_layout = QHBoxLayout()
            row_layout.setContentsMargins(5, 5, 5, 5)
            
            display_field = QLineEdit()
            display_field.setReadOnly(True)
            display_field.setPlaceholderText("Nic nevybráno (vše)")
            display_field.setStyleSheet("background-color: #f0f0f0; color: #333;")
            
            btn = QPushButton("Vybrat...")
            btn.setFixedWidth(80)
            
            def open_dialog():
                dlg = FilterableSelectionDialog(label_text, data_source, self.selection_cache[cache_key], self)
                if dlg.exec_() == QDialog.Accepted:
                    codes, labels = dlg.get_selected_codes()
                    self.selection_cache[cache_key] = codes
                    if labels: display_field.setText(", ".join(labels))
                    else: display_field.clear()
            
            btn.clicked.connect(open_dialog)
            
            row_layout.addWidget(display_field)
            row_layout.addWidget(btn)
            
            if extra_btn:
                row_layout.addWidget(extra_btn)
                
            row_widget.setLayout(row_layout)
            return row_widget

        self.picker_kraj = setup_picker("Kraj", 'kraj', KRAJE)
        layout.addWidget(self.picker_kraj)

        self.picker_okres = setup_picker("Okres", 'okres', OKRESY)
        layout.addWidget(self.picker_okres)

        self.picker_katastr = setup_picker("Katastr", 'katastr', KATASTRY)
        layout.addWidget(self.picker_katastr)

        self.picker_org = setup_picker("Organizace", 'organizace', ORGANIZACE)
        layout.addWidget(self.picker_org)

        self.btn_update_vedouci = QPushButton("🔄")
        self.btn_update_vedouci.setToolTip("Aktualizovat seznam vedoucích z API")
        self.btn_update_vedouci.setFixedWidth(30)
        self.btn_update_vedouci.clicked.connect(self.action_update_vedouci)
        
        self.picker_vedouci = setup_picker("Vedoucí výzkumu", 'vedouci', VEDOUCI, extra_btn=self.btn_update_vedouci)
        layout.addWidget(self.picker_vedouci)

        self.picker_obdobi = setup_picker("Období", 'obdobi', OBDOBI)
        layout.addWidget(self.picker_obdobi)
        
        self.picker_areal = setup_picker("Areál / Druh", 'areal', AREAL)
        layout.addWidget(self.picker_areal)
        
        self.picker_typ = setup_picker("Typ výzkumu", 'typ_akce', TYP_AKCE)
        layout.addWidget(self.picker_typ)

        layout.addStretch(1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
        self.setLayout(layout)

    def action_update_vedouci(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            success, msg = download_vedouci()
            if success:
                count = refresh_vedouci_cache()
                QApplication.restoreOverrideCursor()
                QMessageBox.information(self, "Úspěch", f"{msg}\nNyní je v paměti {count} osob.")
            else:
                QApplication.restoreOverrideCursor()
                QMessageBox.warning(self, "Chyba", f"Nepodařilo se stáhnout data:\n{msg}")
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Chyba", str(e))

    def get_bbox(self):
        return "true" if self.chk_bbox.isChecked() else "false"
        
    def get_filters(self):
        filters = {}
        if self.chk_posevidence.isChecked(): filters['posevidence'] = 'true'
        
        # Loading from cache
        if self.selection_cache['organizace']: filters['f_organizace'] = self.selection_cache['organizace']
        if self.selection_cache['kraj']: filters['f_kraj'] = self.selection_cache['kraj']
        if self.selection_cache['okres']: filters['f_okres'] = self.selection_cache['okres']
        if self.selection_cache['katastr']: filters['f_katastr'] = self.selection_cache['katastr']
        if self.selection_cache['obdobi']: filters['f_obdobi'] = self.selection_cache['obdobi']
        if self.selection_cache['areal']: filters['f_areal'] = self.selection_cache['areal']
        if self.selection_cache['typ_akce']: filters['f_typ_vyzkumu'] = self.selection_cache['typ_akce']
        if self.selection_cache['vedouci']: filters['f_vedouci'] = self.selection_cache['vedouci']
            
        return filters