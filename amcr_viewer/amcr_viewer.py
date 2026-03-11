# -*- coding: utf-8 -*-
from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QMenu, QAction, QToolButton

from .amcr_tools import load_amcr_data
from .amcr_dialog import AmcrFilterDialog
from .resources import *
import os.path

class AmcrViewer:
    
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'AmcrViewer_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

        self.actions = []
        self.menu = self.tr(u'&AMČR Viewer')
        self.first_start = None

    def tr(self, message):
        return QCoreApplication.translate('AmcrViewer', message)

    def add_action(self, icon_path, text, callback, enabled_flag=True,
                   add_to_menu=True, add_to_toolbar=True, status_tip=None,
                   whats_this=None, parent=None):
        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            self.iface.addToolBarIcon(action)

        if add_to_menu:
            self.iface.addPluginToMenu(self.menu, action)

        # Uložíme jen akce, které jdou přímo do QGIS rozhraní
        if add_to_toolbar or add_to_menu:
            self.actions.append(action)
            
        return action

    def initGui(self):
       
        icon_akce_path = os.path.join(self.plugin_dir, 'akce.png')
        icon_lokality_path = os.path.join(self.plugin_dir, 'lokality.png')

        # 1. Vytvoření společného menu
        self.plugin_menu = QMenu()

        # 2. Vytvoření akcí (bez automatického přidání do lišty a menu)
        self.action_download_akce = self.add_action(
            icon_path=icon_akce_path,
            text=self.tr(u'Stáhnout data akcí | AMČR Viewer'),
            callback=lambda checked=False: self.run_download('akce'),
            parent=self.iface.mainWindow(),
            add_to_menu=False,
            add_to_toolbar=False
        )
        self.plugin_menu.addAction(self.action_download_akce)

        self.action_download_lokality = self.add_action(
            icon_path=icon_lokality_path,
            text=self.tr(u'Stáhnout data lokalit | AMČR Viewer'),
            callback=lambda checked=False: self.run_download('lokalita'), 
            parent=self.iface.mainWindow(),
            add_to_menu=False,
            add_to_toolbar=False
        )
        self.plugin_menu.addAction(self.action_download_lokality)

        # 3. Přidání rozbalovacího menu do hlavního menu QGIS
        main_icon = QIcon(icon_akce_path)
        self.main_action = QAction(main_icon, 'AMČR Viewer', self.iface.mainWindow())
        self.main_action.setMenu(self.plugin_menu)
        self.iface.addPluginToMenu(self.menu, self.main_action)

        # 4. Přidání rozevíracího tlačítka do nástrojové lišty (Toolbar)
        self.tool_button = QToolButton()
        self.tool_button.setMenu(self.plugin_menu)
        self.tool_button.setDefaultAction(self.action_download_akce)
        self.tool_button.setPopupMode(QToolButton.MenuButtonPopup)
        
        # Vložení vytvořeného tlačítka do QGIS rozhraní
        self.toolbar_action = self.iface.addToolBarWidget(self.tool_button)
        
        self.first_start = True

    def unload(self):
        # 1. Odstranění vlastního rozbalovacího menu
        if hasattr(self, 'main_action'):
            self.iface.removePluginMenu(self.menu, self.main_action)

        # 2. Odstranění QToolButtonu z nástrojové lišty
        if hasattr(self, 'toolbar_action'):
            self.iface.removeToolBarIcon(self.toolbar_action)

        # 3. Odstranění ostatních běžných akcí
        for action in self.actions:
            self.iface.removePluginMenu(self.menu, action)
            self.iface.removeToolBarIcon(action)
        self.actions.clear()
        
        # 4. Úklid mapového nástroje
        if hasattr(self, 'tool'):
            self.iface.mapCanvas().unsetMapTool(self.tool)

    # --- Data downloading ---
    def run_download(self, typ_dat):
        
        dlg = AmcrFilterDialog(typ_dat)
        result = dlg.exec()
        
        if result == 1:
            filters = dlg.get_filters()
            bbox = dlg.get_bbox()
            komponenty = dlg.get_komponenty()
            
            canvas = self.iface.mapCanvas()
            load_amcr_data(canvas, bbox, filters, typ_dat, komponenty)
