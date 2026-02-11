# -*- coding: utf-8 -*-
from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

from .amcr_tools import load_amcr_data#, AmcrIdentifyTool
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

        self.actions.append(action)
        return action

    def initGui(self):
       
        import os
        plugin_dir = os.path.dirname(__file__)

        icon = QIcon(os.path.join(plugin_dir, 'download.png'))
        
        # icon_info = QIcon(os.path.join(plugin_dir, 'info.png'))

        # Download data button 
        self.action_download = self.add_action(
            icon,
            text=self.tr(u'Načíst data z AMČR'),
            callback=self.run_download,
            parent=self.iface.mainWindow())
        
        # # Info button (Checkable / Toggle)
        # self.action_tool = self.add_action(
        #     icon_info,
        #     text=self.tr(u'Výpis údajů záznamu'),
        #     callback=self.run_tool,
        #     parent=self.iface.mainWindow())
        # self.action_tool.setCheckable(True) # Toto tlačítko se zamačkává

        self.first_start = True

    def unload(self):
        for action in self.actions:
            self.iface.removePluginMenu(self.tr(u'&AMČR Viewer'), action)
            self.iface.removeToolBarIcon(action)
        
        if hasattr(self, 'tool'):
            self.iface.mapCanvas().unsetMapTool(self.tool)

    # --- Data downloading ---
    def run_download(self):
        
        dlg = AmcrFilterDialog()
        result = dlg.exec_()
        
        if result == 1:
            filters = dlg.get_filters()
            bbox = dlg.get_bbox()
            
            canvas = self.iface.mapCanvas()
            load_amcr_data(canvas, bbox, filters)

    # --- Info button toggle ---
    # def run_tool(self):
        
    #     if self.action_tool.isChecked():
    #         canvas = self.iface.mapCanvas()
            
    #         if not hasattr(self, 'tool'):
    #             self.tool = AmcrIdentifyTool(canvas)
    #             self.tool.deactivated.connect(lambda: self.action_tool.setChecked(False))
            
    #         canvas.setMapTool(self.tool)
    #         self.iface.messageBar().pushMessage("AMČR", "Info nástroj aktivní.", level=0)
            
    #     else:
    #         if self.iface.mapCanvas().mapTool() == getattr(self, 'tool', None):
    #             self.iface.mapCanvas().unsetMapTool(self.tool)