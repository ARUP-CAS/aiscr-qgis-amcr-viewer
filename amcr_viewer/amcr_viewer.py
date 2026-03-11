# -*- coding: utf-8 -*-
from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QMenu, QAction, QToolButton

from .amcr_tools import load_amcr_data
from .amcr_dialog import AmcrFilterDialog
from .resources import *
import os.path

class AmcrViewer:
    """
    Main plugin class that manages the GUI elements, menu entries, 
    and coordinates the flow between user input and data processing.
    """
    
    def __init__(self, iface):
        """
        Constructor initializes the connection to QGIS interface and sets up 
        internationalization (i18n).
        """
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        
        # Determine the user's locale to load appropriate translation files
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'AmcrViewer_{}.qm'.format(locale))

        # Install the translator if a translation file for the current locale exists
        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

        # Initialize internal state
        self.actions = []
        self.menu = self.tr(u'&AMČR Viewer')
        self.first_start = None

    def tr(self, message):
        """Helper method for translating strings within the AmcrViewer context."""
        return QCoreApplication.translate('AmcrViewer', message)

    def add_action(self, icon_path, text, callback, enabled_flag=True,
                   add_to_menu=True, add_to_toolbar=True, status_tip=None,
                   whats_this=None, parent=None):
        """
        Helper method to create QActions and automatically register them 
        into the QGIS Menu and Toolbar.
        """
        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        # Standard QGIS API for adding icons and menu items
        if add_to_toolbar:
            self.iface.addToolBarIcon(action)

        if add_to_menu:
            self.iface.addPluginToMenu(self.menu, action)

        # Store only actions that are directly attached to the QGIS UI for later cleanup
        if add_to_toolbar or add_to_menu:
            self.actions.append(action)
            
        return action

    def initGui(self):
        """
        Called when the plugin is loaded. Creates the menu structure, 
        sub-actions, and the dropdown tool button in the toolbar.
        """
        # Define paths for action-specific icons
        icon_akce_path = os.path.join(self.plugin_dir, 'akce.png')
        icon_lokality_path = os.path.join(self.plugin_dir, 'lokality.png')

        # 1. Create a container menu for the plugin
        self.plugin_menu = QMenu()

        # 2. Create sub-actions (Download Projects / Download Sites)
        # add_to_menu/toolbar is False because these go into our custom dropdown menu
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

        # 3. Create the main project action and attach the menu to it
        main_icon = QIcon(icon_akce_path)
        self.main_action = QAction(main_icon, 'AMČR Viewer', self.iface.mainWindow())
        self.main_action.setMenu(self.plugin_menu)
        self.iface.addPluginToMenu(self.menu, self.main_action)

        # 4. Create and configure a QToolButton for the QGIS Toolbar
        # This button acts as a dropdown menu button (MenuButtonPopup)
        self.tool_button = QToolButton()
        self.tool_button.setMenu(self.plugin_menu)
        self.tool_button.setDefaultAction(self.action_download_akce)
        self.tool_button.setPopupMode(QToolButton.MenuButtonPopup)
        
        # Add the widget directly to the toolbar and store the reference for cleanup
        self.toolbar_action = self.iface.addToolBarWidget(self.tool_button)
        
        self.first_start = True

    def unload(self):
        """
        Called when the plugin is disabled or removed. 
        Ensures all GUI elements are removed from QGIS to avoid ghost icons.
        """
        # 1. Remove the custom entry from the main 'Plugins' menu
        if hasattr(self, 'main_action'):
            self.iface.removePluginMenu(self.menu, self.main_action)

        # 2. Remove the custom QToolButton from the toolbar
        if hasattr(self, 'toolbar_action'):
            self.iface.removeToolBarIcon(self.toolbar_action)

        # 3. Clean up any remaining actions registered in self.actions
        for action in self.actions:
            self.iface.removePluginMenu(self.menu, action)
            self.iface.removeToolBarIcon(action)
        self.actions.clear()
        
        # 4. Reset map tools if currently active
        if hasattr(self, 'tool'):
            self.iface.mapCanvas().unsetMapTool(self.tool)

    # --- Data downloading ---
    def run_download(self, typ_dat):
        """
        Triggered by menu/toolbar actions. Opens the filter dialog and 
        hands off the parameters to the data loader.
        """
        # Open the specific filter dialog (Projects vs Sites)
        dlg = AmcrFilterDialog(typ_dat)
        result = dlg.exec()
        
        # If user confirmed the dialog (OK button), gather filters and load data
        if result == 1:
            filters = dlg.get_filters()
            bbox = dlg.get_bbox()
            komponenty = dlg.get_komponenty()
            
            # Access the map canvas and start the fetch/render process from amcr_tools
            canvas = self.iface.mapCanvas()
            load_amcr_data(canvas, bbox, filters, typ_dat, komponenty)