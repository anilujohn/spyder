# -*- coding: utf-8 -*-
#
# Copyright © 2012 Pierre Raybaut
# Licensed under the terms of the MIT License
# (see spyderlib/__init__.py for details)

"""IPython Console plugin

Handles IPython clients (and in the future, will handle IPython kernels too
-- meanwhile, the external console plugin is handling them)"""

# pylint: disable=C0103
# pylint: disable=R0903
# pylint: disable=R0911
# pylint: disable=R0201

from spyderlib.qt.QtGui import (QVBoxLayout, QMessageBox, QWidget, QGroupBox,
                                QLineEdit, QInputDialog, QTabWidget, QMenu,
                                QFontComboBox, QHBoxLayout, QApplication,
                                QToolButton, QLabel, QKeySequence)
from spyderlib.qt.QtCore import SIGNAL, Qt, QUrl

import sys
import re
import os
import os.path as osp
import time

from IPython.config.loader import Config, load_pyconfig_files
from IPython.core.application import get_ipython_dir

# Local imports
from spyderlib.baseconfig import get_conf_path, _
from spyderlib.guiconfig import get_icon
from spyderlib.utils import programs
from spyderlib.utils.misc import get_error_match
from spyderlib.utils.qthelpers import (create_action, create_toolbutton,
                                       add_actions, get_std_icon)
from spyderlib.widgets.tabs import Tabs
from spyderlib.widgets.ipython import IPythonApp
from spyderlib.widgets.findreplace import FindReplace
from spyderlib.plugins import SpyderPluginWidget, PluginConfigPage
from spyderlib.widgets.sourcecode import mixins


class IPythonConsoleConfigPage(PluginConfigPage):
    def __init__(self, plugin, parent):
        PluginConfigPage.__init__(self, plugin, parent)
        self.get_name = lambda: _("IPython console")

    def setup_page(self):
        newcb = self.create_checkbox
        mpl_present = programs.is_module_installed("matplotlib")
        
        # --- Display ---
        font_group = self.create_fontgroup(option=None, text=None,
                                    fontfilters=QFontComboBox.MonospacedFonts)

        # Interface Group
        interface_group = QGroupBox(_("Interface"))
        banner_box = newcb(_("Display initial banner"), 'show_banner',
                      tip=_("This option lets you hide the message shown at\n"
                            "the top of the console when it's opened."))
        gui_comp_box = newcb(_("Use a completion widget"),
                             'use_gui_completion',
                             tip=_("Use a widget instead of plain text "
                                   "output for tab completion"))
        pager_box = newcb(_("Use a pager to display additional text inside "
                            "the console"), 'use_pager',
                            tip=_("Useful if you don't want to fill the "
                                  "console with long help or completion texts.\n"
                                  "Note: Use the Q key to get out of the "
                                  "pager."))
        calltips_box = newcb(_("Display balloon tips"), 'show_calltips')
        ask_box = newcb(_("Ask for confirmation before closing"),
                        'ask_before_closing')

        interface_layout = QVBoxLayout()
        interface_layout.addWidget(banner_box)
        interface_layout.addWidget(gui_comp_box)
        interface_layout.addWidget(pager_box)
        interface_layout.addWidget(calltips_box)
        interface_layout.addWidget(ask_box)
        interface_group.setLayout(interface_layout)
        
        # Background Color Group
        bg_group = QGroupBox(_("Background color"))
        light_radio = self.create_radiobutton(_("Light background"),
                                              'light_color')
        dark_radio = self.create_radiobutton(_("Dark background"),
                                             'dark_color')
        bg_layout = QVBoxLayout()
        bg_layout.addWidget(light_radio)
        bg_layout.addWidget(dark_radio)
        bg_group.setLayout(bg_layout)

        # Source Code Group
        source_code_group = QGroupBox(_("Source code"))
        buffer_spin = self.create_spinbox(
                _("Buffer:  "), _(" lines"),
                'buffer_size', min_=-1, max_=1000000, step=100,
                tip=_("Set the maximum number of lines of text shown in the\n"
                      "console before truncation. Specifying -1 disables it\n"
                      "(not recommended!)"))
        source_code_layout = QVBoxLayout()
        source_code_layout.addWidget(buffer_spin)
        source_code_group.setLayout(source_code_layout)
        
        # --- Graphics ---
        # Pylab Group
        pylab_group = QGroupBox(_("Support for graphics (Pylab)"))
        pylab_box = newcb(_("Activate support"), 'pylab')
        autoload_pylab_box = newcb(_("Automatically load Pylab and NumPy"),
                               'pylab/autoload',
                               tip=_("This lets you load graphics support "
                                     "without importing \nthe commands to do "
                                     "plots. Useful to work with other\n"
                                     "plotting libraries different to "
                                     "Matplotlib or to develop \nGUIs with "
                                     "Spyder."))
        autoload_pylab_box.setEnabled(self.get_option('pylab') and mpl_present)
        self.connect(pylab_box, SIGNAL("toggled(bool)"),
                     autoload_pylab_box.setEnabled)
        
        pylab_layout = QVBoxLayout()
        pylab_layout.addWidget(pylab_box)
        pylab_layout.addWidget(autoload_pylab_box)
        pylab_group.setLayout(pylab_layout)
        
        if not mpl_present:
            self.set_option('pylab', False)
            self.set_option('pylab/autoload', False)
            pylab_group.setEnabled(False)
            pylab_tip = _("This feature requires the Matplotlib library.\n"
                          "It seems you don't have it installed.")
            pylab_box.setToolTip(pylab_tip)
        
        # Pylab backend Group
        inline = _("Inline")
        automatic = _("Automatic")
        backend_group = QGroupBox(_("Graphics backend"))
        bend_label = QLabel(_("Decide how graphics are going to be displayed "
                              "in the console. If unsure, please select "
                              "<b>%s</b> to put graphics inside the "
                              "console or <b>%s</b> to interact with "
                              "them (through zooming and panning) in a "
                              "separate window.") % (inline, automatic))
        bend_label.setWordWrap(True)

        backends = [(inline, 0), (automatic, 1), ("Qt", 2)]
        # TODO: Add gtk3 when 0.13 is released
        if sys.platform == 'darwin':
            backends.append( ("Mac OSX", 3) )
        if programs.is_module_installed('pygtk'):
            backends.append( ("Gtk", 4) )
        if programs.is_module_installed('wxPython'):
            backends.append( ("Wx", 5) )
        if programs.is_module_installed('_tkinter'):
            backends.append( ("Tkinter", 6) )
        backends = tuple(backends)
        
        backend_box = self.create_combobox( _("Backend:")+"   ", backends,
                                       'pylab/backend', default=0,
                                       tip=_("This option will be applied the "
                                             "next time a console is opened."))
        
        backend_layout = QVBoxLayout()
        backend_layout.addWidget(bend_label)
        backend_layout.addWidget(backend_box)
        backend_group.setLayout(backend_layout)
        backend_group.setEnabled(self.get_option('pylab') and mpl_present)
        self.connect(pylab_box, SIGNAL("toggled(bool)"),
                     backend_group.setEnabled)
        
        # Inline backend Group
        inline_group = QGroupBox(_("Inline backend"))
        inline_label = QLabel(_("Decide how to render the figures created by "
                                "this backend"))
        inline_label.setWordWrap(True)
        formats = (("PNG", 0), ("SVG", 1))
        format_box = self.create_combobox(_("Format:")+"   ", formats,
                                       'pylab/inline/figure_format', default=0)
        resolution_spin = self.create_spinbox(
                          _("Resolution:")+"  ", " "+_("dpi"),
                          'pylab/inline/resolution', min_=56, max_=112, step=1,
                          tip=_("Only used when the format is PNG. Default is "
                                "72"))
        width_spin = self.create_spinbox(
                          _("Width:")+"  ", " "+_("inches"),
                          'pylab/inline/width', min_=4, max_=20, step=1,
                          tip=_("Default is 6"))
        height_spin = self.create_spinbox(
                          _("Height:")+"  ", " "+_("inches"),
                          'pylab/inline/height', min_=4, max_=20, step=1,
                          tip=_("Default is 4"))
        
        inline_layout = QVBoxLayout()
        inline_layout.addWidget(inline_label)
        inline_layout.addWidget(format_box)
        inline_layout.addWidget(resolution_spin)
        inline_layout.addWidget(width_spin)
        inline_layout.addWidget(height_spin)
        inline_group.setLayout(inline_layout)
        inline_group.setEnabled(self.get_option('pylab') and mpl_present)
        self.connect(pylab_box, SIGNAL("toggled(bool)"),
                     inline_group.setEnabled)

        # --- Startup ---
        # Run lines Group
        run_lines_group = QGroupBox(_("Run code"))
        run_lines_label = QLabel(_("You can run several lines of code when "
                                   "a console is started. Please introduce "
                                   "each one separated by commas, for "
                                   "example:<br>"
                                   "<i>import os, import sys</i>"))
        run_lines_label.setWordWrap(True)
        run_lines_edit = self.create_lineedit(_("Lines:"), 'startup/run_lines',
                                              '', alignment=Qt.Horizontal)
        
        run_lines_layout = QVBoxLayout()
        run_lines_layout.addWidget(run_lines_label)
        run_lines_layout.addWidget(run_lines_edit)
        run_lines_group.setLayout(run_lines_layout)
        
        # Run file Group
        run_file_group = QGroupBox(_("Run a file"))
        run_file_label = QLabel(_("You can also run a whole file at startup "
                                  "instead of just some lines (This is "
                                  "similar to have a PYTHONSTARTUP file)."))
        run_file_label.setWordWrap(True)
        file_radio = newcb(_("Use the following file:"),
                           'startup/use_run_file', False)
        run_file_browser = self.create_browsefile('', 'startup/run_file', '')
        run_file_browser.setEnabled(False)
        self.connect(file_radio, SIGNAL("toggled(bool)"),
                     run_file_browser.setEnabled)
        
        run_file_layout = QVBoxLayout()
        run_file_layout.addWidget(run_file_label)
        run_file_layout.addWidget(file_radio)
        run_file_layout.addWidget(run_file_browser)
        run_file_group.setLayout(run_file_layout)
        
        # Spyder group
        spyder_group = QGroupBox(_("Spyder startup"))
        ipystartup_box = newcb(_("Open an IPython console at startup"),
                                 "open_ipython_at_startup")
        spyder_layout = QVBoxLayout()
        spyder_layout.addWidget(ipystartup_box)
        spyder_group.setLayout(spyder_layout)
        
        # ---- Advanced settings ----
        # Greedy completer group
        greedy_group = QGroupBox(_("Greedy completion"))
        greedy_label = QLabel(_("Enable <tt>Tab</tt> completion on elements "
                                "of lists, results of function calls, etc, "
                                "<i>without</i> assigning them to a "
                                "variable.<br>"
                                "For example, you can get completions on "
                                "things like <tt>li[0].&lt;Tab&gt;</tt> or "
                                "<tt>ins.meth().&lt;Tab&gt;</tt>"))
        greedy_label.setWordWrap(True)
        greedy_box = newcb(_("Use the greedy completer"), "greedy_completer",
                           tip="<b>Warning</b>: It can be unsafe because the "
                                "code is actually evaluated when you press "
                                "<tt>Tab</tt>.")
        
        greedy_layout = QVBoxLayout()
        greedy_layout.addWidget(greedy_label)
        greedy_layout.addWidget(greedy_box)
        greedy_group.setLayout(greedy_layout)
        
        # Autocall group
        autocall_group = QGroupBox(_("Autocall"))
        autocall_label = QLabel(_("Autocall makes IPython automatically call "
                                "any callable object even if you didn't type "
                                "explicit parentheses.<br>"
                                "For example, if you type <i>str 43</i> it "
                                "becomes <i>str(43)</i> automatically."))
        autocall_label.setWordWrap(True)
        
        autocall_opts = (('Off', 0), ('Smart', 1), ('Full', 2))
        autocall_box = self.create_combobox(
                         "Autocall:  ", autocall_opts, 'autocall', default = 0,
                         tip=_("On <b>Smart</b> mode, Autocall is not applied "
                               "if there are no arguments after the callable. "
                               "On <b>Full</b> mode, all callable objects are "
                               "automatically called (even if no arguments "
                               "are present)."))
        
        autocall_layout = QVBoxLayout()
        autocall_layout.addWidget(autocall_label)
        autocall_layout.addWidget(autocall_box)
        autocall_group.setLayout(autocall_layout)
        
        # Sympy group
        sympy_group = QGroupBox(_("Symbolic Mathematics"))
        sympy_label = QLabel(_("Perfom symbolic operations in the console "
                               "(e.g. integrals, derivatives, vector calculus, "
                               "etc) and get the outputs in a beautifully "
                               "printed style."))
        sympy_label.setWordWrap(True)
        sympy_box = newcb(_("Use symbolic math"), "symbolic_math",
                          tip="This option loads the Sympy library to work "
                              "with.<br>Please refer to its documentation to "
                              "learn how to use it.")
        
        sympy_layout = QVBoxLayout()
        sympy_layout.addWidget(sympy_label)
        sympy_layout.addWidget(sympy_box)
        sympy_group.setLayout(sympy_layout)
        
        sympy_present = programs.is_module_installed("sympy")
        if not sympy_present:
            self.set_option("symbolic_math", False)
            sympy_box.setEnabled(False)
            sympy_tip = _("This feature requires the Sympy library.\n"
                          "It seems you don't have it installed.")
            sympy_box.setToolTip(sympy_tip)
        
        # Prompts group
        prompts_group = QGroupBox(_("Prompts"))
        prompts_label = QLabel(_("Modify how Input and Output prompts are "
                                 "shown in the console."))
        prompts_label.setWordWrap(True)
        in_prompt_edit = self.create_lineedit(_("Input prompt:"),
                                    'in_prompt', '',
                                  _('Default is<br>'
                                    'In [&lt;span class="in-prompt-number"&gt;'
                                    '%i&lt;/span&gt;]:'),
                                    alignment=Qt.Horizontal)
        out_prompt_edit = self.create_lineedit(_("Output prompt:"),
                                   'out_prompt', '',
                                 _('Default is<br>'
                                   'Out[&lt;span class="out-prompt-number"&gt;'
                                   '%i&lt;/span&gt;]:'),
                                   alignment=Qt.Horizontal)
        
        prompts_layout = QVBoxLayout()
        prompts_layout.addWidget(prompts_label)
        prompts_layout.addWidget(in_prompt_edit)
        prompts_layout.addWidget(out_prompt_edit)
        prompts_group.setLayout(prompts_layout)

        # --- Tabs organization ---
        tabs = QTabWidget()
        tabs.addTab(self.create_tab(font_group, interface_group, bg_group,
                                    source_code_group), _("Display"))
        tabs.addTab(self.create_tab(pylab_group, backend_group, inline_group),
                                    _("Graphics"))
        tabs.addTab(self.create_tab(spyder_group, run_lines_group,
                                    run_file_group), _("Startup"))
        tabs.addTab(self.create_tab(greedy_group, autocall_group, sympy_group,
                                    prompts_group), _("Advanced Settings"))

        vlayout = QVBoxLayout()
        vlayout.addWidget(tabs)
        self.setLayout(vlayout)


#XXX: For now, we add this layer to the IPython widget (which is the
#     `ipython_widget` attribute of this `IPythonClient` class) even if this is
#     quite featureless: the IPythonClient has a vertical layout which contains
#     only the IPython widget inside it. So we could have directly made the 
#     IPythonClient class inherit from the IPython widget's class. However,
#     the latter is not yet clearly defined: IPython API is quite unclear and 
#     confusing for this matter, so I prefered to add this layer. But that's 
#     just a start: we should replace it by the correct inheritance logic in 
#     time.
class IPythonClient(QWidget, mixins.SaveHistoryMixin):
    """Spyder IPython client (or frontend)"""
    
    CONF_SECTION = 'ipython'
    SEPARATOR = '%s##---(%s)---' % (os.linesep*2, time.ctime())
    
    def __init__(self, plugin, connection_file, kernel_widget_id, client_name,
                 ipython_widget, history_filename, menu_actions=None):
        super(IPythonClient, self).__init__(plugin)
        mixins.SaveHistoryMixin.__init__(self)
        self.options_button = None

        self.connection_file = connection_file
        self.kernel_widget_id = kernel_widget_id
        self.client_name = client_name        
        self.ipython_widget = ipython_widget
        self.menu_actions = menu_actions
        self.history_filename = get_conf_path(history_filename)
        self.history = []
        
        vlayout = QVBoxLayout()
        toolbar_buttons = self.get_toolbar_buttons()
        hlayout = QHBoxLayout()
        for button in toolbar_buttons:
            hlayout.addWidget(button)
        vlayout.addLayout(hlayout)
        vlayout.setContentsMargins(0, 0, 0, 0)
        vlayout.addWidget(self.ipython_widget)
        self.setLayout(vlayout)
        
        self.exit_callback = lambda: plugin.close_console(widget=self)

        # Connect the IPython widget to this IPython client:
        # (see spyderlib/widgets/ipython.py for more details about this)
        ipython_widget.set_ipython_client(self)
        
        # To save history
        self.ipython_widget.executing.connect(
                                      lambda c: self.add_to_history(command=c))
        
        # To update history after execution
        self.ipython_widget.executed.connect(self.update_history)
        
    #------ Public API --------------------------------------------------------
    def get_name(self):
        """Return client name"""
        return _("Console") + " " + self.client_name
    
    def get_control(self):
        """Return the text widget (or similar) to give focus to"""
        # page_control is the widget used for paging
        page_control = self.ipython_widget._page_control
        if page_control and page_control.isVisible():
            return page_control
        else:
            return self.ipython_widget._control

    def get_options_menu(self):
        """Return options menu"""
        # Kernel
        self.interrupt_action = create_action(self, _("Interrupt kernel"),
                                              icon=get_icon('terminate.png'),
                                              triggered=self.interrupt_kernel)
        self.restart_action = create_action(self, _("Restart kernel"),
                                            icon=get_icon('restart.png'),
                                            triggered=self.restart_kernel)
        
        # Help
        self.intro_action = create_action(self, _("Intro to IPython"),
                                          triggered=self._show_intro)
        self.quickref_action = create_action(self, _("Quick Reference"),
                                             triggered=self._show_quickref)
        self.guiref_action = create_action(self, _("Console help"),
                                           triggered=self._show_guiref)                    
        help_menu = QMenu(_("Help"), self)
        help_action = create_action(self, _("IPython Help"),
                                    icon=get_std_icon('DialogHelpButton'))
        help_action.setMenu(help_menu)
        add_actions(help_menu, (self.intro_action, self.guiref_action,
                                self.quickref_action))
        
        # Main menu
        if self.menu_actions is not None:
            actions = [self.interrupt_action, self.restart_action, None] +\
                      self.menu_actions + [None, help_menu]
        else:
            actions = [self.interrupt_action, self.restart_action, None,
                       help_menu]
        return actions
    
    def get_toolbar_buttons(self):
        """Return toolbar buttons list"""
        #TODO: Eventually add some buttons (Empty for now)
        # (see for example: spyderlib/widgets/externalshell/baseshell.py)
        buttons = []
        if self.options_button is None:
            options = self.get_options_menu()
            if options:
                self.options_button = create_toolbutton(self,
                        text=_("Options"), icon=get_icon('tooloptions.png'))
                self.options_button.setPopupMode(QToolButton.InstantPopup)
                menu = QMenu(self)
                add_actions(menu, options)
                self.options_button.setMenu(menu)
        if self.options_button is not None:
            buttons.append(self.options_button)
        return buttons
    
    def add_actions_to_context_menu(self, menu):
        """Add actions to IPython widget context menu"""
        # See spyderlib/widgets/ipython.py for more details on this method
        inspect_action = create_action(self, _("Inspect current object"),
                                    QKeySequence("Ctrl+I"),
                                    icon=get_std_icon('MessageBoxInformation'),
                                    triggered=self.inspect_object)
        clear_line_action = create_action(self, _("Clear line or block"),
                                          QKeySequence("Shift+Escape"),
                                          icon=get_icon('eraser.png'),
                                          triggered=self.clear_line)
        clear_console_action = create_action(self, _("Clear console"),
                                             QKeySequence("Ctrl+L"),
                                             icon=get_icon('clear.png'),
                                             triggered=self.clear_console)
        quit_action = create_action(self, _("&Quit"), icon='exit.png',
                                    triggered=self.exit_callback)
        add_actions(menu, (None, inspect_action, clear_line_action,
                           clear_console_action, None, quit_action))
        return menu
    
    def set_font(self, font):
        """Set IPython widget's font"""
        self.ipython_widget.font = font
    
    def interrupt_kernel(self):
        """Interrupt the associanted Spyder kernel if it's running"""
        self.ipython_widget.request_interrupt_kernel()
    
    def restart_kernel(self):
        """Restart the associanted Spyder kernel"""
        self.ipython_widget.request_restart_kernel()
    
    def inspect_object(self):
        """Show how to inspect an object with our object inspector"""
        self.ipython_widget._control.inspect_current_object()
    
    def clear_line(self):
        """Clear a console line"""
        self.ipython_widget._keyboard_quit()
    
    def clear_console(self):
        """Clear the whole console"""
        self.ipython_widget.execute("%clear")
    
    def if_kernel_dies(self, t):
        """
        Show a message in the console if the kernel dies.
        t is the time in seconds between the death and showing the message.
        """
        message = _("It seems the kernel died unexpectedly. Use "
                    "'Restart kernel' to continue using this console.")
        self.ipython_widget._append_plain_text(message + '\n')
    
    def update_history(self):
        self.history = self.ipython_widget._history
    
    def interrupt_message(self):
        """
        Print an interrupt message when the client is connected to an external
        kernel
        """
        message = _("Kernel process is either remote or unspecified. "
                    "Cannot interrupt")
        QMessageBox.information(self, "IPython", message)
    
    def restart_message(self):
        """
        Print a restart message when the client is connected to an external
        kernel
        """
        message = _("Kernel process is either remote or unspecified. "
                    "Cannot restart.")
        QMessageBox.information(self, "IPython", message)
    
    #------ Private API -------------------------------------------------------
    def _show_rich_help(self, text):
        """Use our Object Inspector to show IPython help texts in rich mode"""
        from spyderlib.utils.inspector import sphinxify as spx
        
        context = spx.generate_context(title='', argspec='', note='',
                                       math=False)
        html_text = spx.sphinxify(text, context)
        inspector = self.get_control().inspector
        inspector.switch_to_rich_text()
        inspector.set_rich_text_html(html_text,
                                     QUrl.fromLocalFile(spx.CSS_PATH))
    
    def _show_plain_help(self, text):
        """Use our Object Inspector to show IPython help texts in plain mode"""
        inspector = self.get_control().inspector
        inspector.switch_to_plain_text()
        inspector.set_plain_text(text, is_code=False)
    
    def _show_intro(self):
        """Show intro to IPython help"""
        from IPython.core.usage import interactive_usage
        self._show_rich_help(interactive_usage)
    
    def _show_guiref(self):
        """Show qtconsole help"""
        from IPython.core.usage import gui_reference
        self._show_rich_help(gui_reference)
    
    def _show_quickref(self):
        """Show IPython Cheat Sheet"""
        from IPython.core.usage import quick_reference
        self._show_plain_help(quick_reference)
    
    #---- Qt methods ----------------------------------------------------------
    def closeEvent(self, event):
        """Reimplement Qt method to stop sending the custom_restart_kernel_died
        signal"""
        self.ipython_widget.custom_restart = False
            

class IPythonConsole(SpyderPluginWidget):
    """IPython Console plugin"""
    CONF_SECTION = 'ipython_console'
    CONFIGWIDGET_CLASS = IPythonConsoleConfigPage
    def __init__(self, parent):
        SpyderPluginWidget.__init__(self, parent)
        
        self.ipython_app = None
        self.initialize_application()

        self.tabwidget = None
        self.menu_actions = None
        
        self.inspector = None # Object inspector plugin
        self.historylog = None # History log plugin
        
        self.shellwidgets = []
        
        # Initialize plugin
        self.initialize_plugin()
        
        layout = QVBoxLayout()
        self.tabwidget = Tabs(self, self.menu_actions)
        if hasattr(self.tabwidget, 'setDocumentMode')\
           and not sys.platform == 'darwin':
            # Don't set document mode to true on OSX because it generates
            # a crash when the console is detached from the main window
            # Fixes Issue 561
            self.tabwidget.setDocumentMode(True)
        self.connect(self.tabwidget, SIGNAL('currentChanged(int)'),
                     self.refresh_plugin)
        self.connect(self.tabwidget, SIGNAL('move_data(int,int)'),
                     self.move_tab)
                     
        self.tabwidget.set_close_function(self.close_console)

        layout.addWidget(self.tabwidget)

        # Find/replace widget
        self.find_widget = FindReplace(self)
        self.find_widget.hide()
        self.register_widget_shortcuts("Editor", self.find_widget)
        layout.addWidget(self.find_widget)
        
        self.setLayout(layout)
            
        # Accepting drops
        self.setAcceptDrops(True)
    
    #------ SpyderPluginWidget API --------------------------------------------
    def get_plugin_title(self):
        """Return widget title"""
        return _('IPython console')
    
    def get_plugin_icon(self):
        """Return widget icon"""
        return get_icon('ipython_console.png')
    
    def get_focus_widget(self):
        """
        Return the widget to give focus to when
        this plugin's dockwidget is raised on top-level
        """
        shellwidget = self.tabwidget.currentWidget()
        if shellwidget is not None:
            return shellwidget.get_control()
        
    def get_plugin_actions(self):
        """Return a list of actions related to plugin"""
        client_action = create_action(self, _("Connect to an existing kernel"),
                None,
                'ipython_console.png',
                _("Open a new IPython client connected to an external kernel"),
                triggered=self.new_client)
        
        # Add the action to the 'Interpreters' menu on the main window
        interact_menu_actions = [None, client_action]
        self.main.interact_menu_actions += interact_menu_actions
        
        # Plugin actions
        console = self.main.extconsole
        self.menu_actions = [console.ipython_kernel_action, client_action]
        
        return self.menu_actions
    
    def register_plugin(self):
        """Register plugin in Spyder's main window"""
        self.main.add_dockwidget(self)
        self.inspector = self.main.inspector
        self.historylog = self.main.historylog
        self.connect(self, SIGNAL('focus_changed()'),
                     self.main.plugin_focus_changed)
        if self.main.editor:
            self.connect(self, SIGNAL("edit_goto(QString,int,QString)"),
                         self.main.editor.load)
        
    def closing_plugin(self, cancelable=False):
        """Perform actions before parent main window is closed"""
        for shellwidget in self.shellwidgets:
            shellwidget.close()
        return True
    
    def refresh_plugin(self):
        """Refresh tabwidget"""
        clientwidget = None
        if self.tabwidget.count():
            # Give focus to the control widget of selected tab 
            clientwidget = self.tabwidget.currentWidget()
            control = clientwidget.get_control()
            control.setFocus()
            widgets = clientwidget.get_toolbar_buttons()+[5]
            
            # Change extconsole tab to the client's kernel widget
            idx = self.main.extconsole.get_shell_index_from_id(
                                                 clientwidget.kernel_widget_id)
            if idx is not None:
                self.main.extconsole.tabwidget.setCurrentIndex(idx)
        else:
            control = None
            widgets = []
        self.find_widget.set_editor(control)
        self.tabwidget.set_corner_widgets({Qt.TopRightCorner: widgets})
        self.emit(SIGNAL('update_plugin_title()'))
    
    def apply_plugin_settings(self, options):
        """Apply configuration file's plugin settings"""
        font = self.get_plugin_font()
        for shellwidget in self.shellwidgets:
            shellwidget.set_font(font)
    
    #------ Public API --------------------------------------------------------
    def get_clients(self):
        """Return IPython client widgets list"""
        return [sw for sw in self.shellwidgets
                if isinstance(sw, IPythonClient)]
        
#    def get_kernels(self):
#        """Return IPython kernel widgets list"""
#        return [sw for sw in self.shellwidgets
#                if isinstance(sw, IPythonKernel)]
#        

    def get_focus_client(self):
        """Return client shellwidget which has focus, if any"""
        widget = QApplication.focusWidget()
        for client in self.get_clients():
            if widget is client or widget is client.get_control():
                return client

    def new_client(self, connection_file=None, kernel_widget_id=None):
        """Create a new IPython client"""
        cf = connection_file
        if cf is None:
            example = _('(for example: `kernel-3764.json`, or simply `3764`)')
            while True:
                cf, valid = QInputDialog.getText(self, _('IPython'),
                              _('Provide an IPython kernel connection file:')+\
                              '\n'+example,
                              QLineEdit.Normal)
                if valid:
                    cf = str(cf)
                    match = re.match('(kernel-|^)([a-fA-F0-9-]+)(.json|$)', cf)
                    kernel_num = match.groups()[1]
                    if kernel_num:
                        cf = 'kernel-%s.json' % kernel_num
                        break
                else:
                    return

        # Generating the client name and setting kernel_widget_id
        match = re.match('^kernel-([a-fA-F0-9-]+).json', cf)
        count = 0
        while True:
            client_name = match.groups()[0]+'/'+chr(65+count)
            for clw in self.get_clients():
                if clw.client_name == client_name:
                    kernel_widget_id = clw.kernel_widget_id
                    break
            else:
                break
            count += 1
        
        # Trying to get kernel_widget_id from the currently opened kernels if
        # the previous procedure fails. This could happen when the first
        # client connected to a kernel is closed but the kernel is left open
        # and you try to connect new clients to it
        if kernel_widget_id is None:
            console = self.main.extconsole
            for sw in console.shellwidgets:
                if sw.connection_file == cf:
                    kernel_widget_id = id(sw)

        # Creating the IPython client widget
        try:
            self.register_client(cf, kernel_widget_id, client_name)
        except (IOError, UnboundLocalError):
            QMessageBox.critical(self, _('IPython'),
                                 _("Unable to connect to IPython kernel "
                                   "<b>`%s`") % cf)
            return

    def client_config(self):
        """Generate a Config instance for IPython clients using our config
        system
        
        This let us create each client with its own config (as oppossed to
        IPythonQtConsoleApp, where all clients have the same config)
        """
        # ---- IPython config ----
        try:
            profile_path = osp.join(get_ipython_dir(), 'profile_default')
            full_ip_cfg = load_pyconfig_files(['ipython_qtconsole_config.py'],
                                              profile_path)
            
            # From the full config we only select the IPythonWidget section
            # because the others have no effect here.
            ip_cfg = Config({'IPythonWidget': full_ip_cfg.IPythonWidget})
        except:
            ip_cfg = Config()
       
        # ---- Spyder config ----
        spy_cfg = Config()
        
        # Make the pager widget a rich one (i.e a QTextEdit)
        spy_cfg.IPythonWidget.kind = 'rich'
        
        # Gui completion widget
        gui_comp_o = self.get_option('use_gui_completion')
        completions = {True: 'droplist', False: 'ncurses'}
        spy_cfg.IPythonWidget.gui_completion = completions[gui_comp_o]

        # Pager
        pager_o = self.get_option('use_pager')
        if pager_o:
            spy_cfg.IPythonWidget.paging = 'inside'
        else:
            spy_cfg.IPythonWidget.paging = 'none'
        
        # Calltips
        calltips_o = self.get_option('show_calltips')
        spy_cfg.IPythonWidget.enable_calltips = calltips_o

        # Buffer size
        buffer_size_o = self.get_option('buffer_size')
        spy_cfg.IPythonWidget.buffer_size = buffer_size_o
        
        # Prompts
        in_prompt_o = self.get_option('in_prompt')
        out_prompt_o = self.get_option('out_prompt')
        if in_prompt_o:
            spy_cfg.IPythonWidget.in_prompt = in_prompt_o
        if out_prompt_o:
            spy_cfg.IPythonWidget.out_prompt = out_prompt_o
        
        # Merge IPython and Spyder configs. Spyder prefs will have prevalence
        # over IPython ones
        ip_cfg._merge(spy_cfg)
        return ip_cfg
    
    def initialize_application(self):
        """Initialize IPython application"""
        #======================================================================
        # For IPython developers review [1]
        self.ipython_app = IPythonApp()
        # Is the following line really necessary?
        #self.ipython_app.initialize_all_except_qt()
        #======================================================================

    def register_client(self, connection_file, kernel_widget_id, client_name):
        """Register new IPython client"""
        #======================================================================
        # For IPython developers review [2]
        ipython_widget = self.ipython_app.create_new_client(connection_file,
                                                   config=self.client_config())
        #======================================================================

        shellwidget = IPythonClient(self, connection_file, kernel_widget_id,
                                    client_name, ipython_widget,
                                    history_filename='.history.py',
                                    menu_actions=self.menu_actions)
        # QTextEdit Widgets
        control = shellwidget.ipython_widget._control
        page_control = shellwidget.ipython_widget._page_control
        
        # For tracebacks
        self.connect(control, SIGNAL("go_to_error(QString)"), self.go_to_error)

        # Handle kernel interrupt
        extconsoles = self.main.extconsole.shellwidgets
        spyder_kernel = None
        if extconsoles:
            if extconsoles[-1].connection_file == connection_file:
                spyder_kernel = extconsoles[-1]
                ipython_widget.custom_interrupt_requested.connect(
                                              spyder_kernel.keyboard_interrupt)
        if spyder_kernel is None:
            ipython_widget.custom_interrupt_requested.connect(
                                                 shellwidget.interrupt_message)
        
        # Handle kernel restarts asked by the user
        if spyder_kernel is not None:
            ipython_widget.custom_restart_requested.connect(
                                                        self.create_new_kernel)
        else:
            ipython_widget.custom_restart_requested.connect(
                                                   shellwidget.restart_message)
        
        # Print a message if kernel dies unexpectedly
        ipython_widget.custom_restart_kernel_died.connect(
                                       lambda t: shellwidget.if_kernel_dies(t))
        
        # Connect text widget to our inspector
        if spyder_kernel is not None and self.inspector is not None:
            control.set_inspector(self.inspector)
        
        # Connect client to our history log
        if self.historylog is not None:
            self.historylog.add_history(shellwidget.history_filename)
            self.connect(shellwidget,
                         SIGNAL('append_to_history(QString,QString)'),
                         self.historylog.append_to_history)
        
        # Apply settings to newly created client widget:
        shellwidget.set_font( self.get_plugin_font() )
        
        # Add tab and change focus to it
        self.add_tab(shellwidget, name=shellwidget.get_name())
        self.connect(shellwidget, SIGNAL('focus_changed()'),
                     lambda: self.emit(SIGNAL('focus_changed()')))
        
        # Update the find widget if focus changes between control and
        # page_control
        self.find_widget.set_editor(control)
        if page_control:
            self.connect(control, SIGNAL('visibility_changed(bool)'),
                         self.refresh_plugin)
            self.connect(page_control, SIGNAL('visibility_changed(bool)'),
                         self.refresh_plugin)
            self.connect(page_control, SIGNAL('show_find_widget()'),
                         self.find_widget.show)
    
    def close_related_ipython_clients(self, client):
        """Close all IPython clients related to *client*, except itself"""
        for clw in self.shellwidgets[:]:
            if clw is not client and\
               clw.connection_file == client.connection_file:
                self.close_console(widget=clw)
    
    def get_ipython_widget(self, kernel_widget_id):
        """Return IPython widget (ipython_plugin.ipython_widget) 
        associated to kernel_widget_id"""
        for clw in self.shellwidgets:
            if clw.kernel_widget_id == kernel_widget_id:
                return clw.ipython_widget
        else:
            raise ValueError, "Unknown kernel widget ID %r" % kernel_widget_id
        
    def add_tab(self, widget, name):
        """Add tab"""
        self.shellwidgets.append(widget)
        index = self.tabwidget.addTab(widget, get_icon('ipython_console.png'),
                                      name)
        self.tabwidget.setCurrentIndex(index)
        if self.dockwidget and not self.ismaximized:
            self.dockwidget.setVisible(True)
            self.dockwidget.raise_()
        widget.get_control().setFocus()
        
    def move_tab(self, index_from, index_to):
        """
        Move tab (tabs themselves have already been moved by the tabwidget)
        """
        shell = self.shellwidgets.pop(index_from)
        self.shellwidgets.insert(index_to, shell)
        self.emit(SIGNAL('update_plugin_title()'))
        
    def close_console(self, index=None, widget=None, force=False):
        """Close console tab from index or widget (or close current tab)"""
        if not self.tabwidget.count():
            return
        if widget is not None:
            index = self.tabwidget.indexOf(widget)
        if index is None and widget is None:
            index = self.tabwidget.currentIndex()
        if index is not None:
            widget = self.tabwidget.widget(index)

        # Check if related clients or kernels are opened
        # and eventually ask before closing them
        if not force and isinstance(widget, IPythonClient):
            console = self.main.extconsole
            idx = console.get_shell_index_from_id(widget.kernel_widget_id)
            if idx is not None:
                close_all = True
                if self.get_option('ask_before_closing'):
                    ans = QMessageBox.question(self, self.get_plugin_title(),
                           _("%s will be closed.\n"
                             "Do you want to kill the associated kernel "
                             "and all of its clients?") % widget.get_name(),
                           QMessageBox.Yes|QMessageBox.No|QMessageBox.Cancel)
                    if ans == QMessageBox.Cancel:
                        return
                    close_all = ans == QMessageBox.Yes
                if close_all:
                    console.close_console(index=idx, from_ipython_client=True)
                    self.close_related_ipython_clients(widget)
        widget.close()
        
        # Note: widget index may have changed after closing related widgets
        self.tabwidget.removeTab(self.tabwidget.indexOf(widget))
        self.shellwidgets.remove(widget)

        self.emit(SIGNAL('update_plugin_title()'))
        
    def go_to_error(self, text):
        """Go to error if relevant"""
        match = get_error_match(unicode(text))
        if match:
            fname, lnb = match.groups()
            self.emit(SIGNAL("edit_goto(QString,int,QString)"),
                      osp.abspath(fname), int(lnb), '')
    
    def get_shell_index_from_id(self, shell_id):
        """Return shellwidget index from id"""
        for index, shell in enumerate(self.shellwidgets):
            if id(shell) == shell_id:
                return index
    
    def rename_ipython_client_tab(self, connection_file, client_widget_id):
        """Add the pid of the kernel process to an IPython client tab"""
        index = self.get_shell_index_from_id(client_widget_id)
        match = re.match('^kernel-(\d+).json', connection_file)
        if match is not None:  # should not fail, but we never know...
            name = _("Console") + " " + match.groups()[0] + '/' + chr(65)
            self.tabwidget.setTabText(index, name)
    
    def create_new_kernel(self):
        """Create a new kernel if the user asks for it"""
        # Took this bit of code (until if result == ) from the IPython project
        # (frontend/qt/frontend_widget.py - restart_kernel).
        # Licensed under the BSD license
        message = _('Are you sure you want to restart the kernel?')
        buttons = QMessageBox.Yes | QMessageBox.No
        result = QMessageBox.question(self, _('Restart kernel?'),
                                      message, buttons)
        if result == QMessageBox.Yes:
            console = self.main.extconsole
            console.start_ipython_kernel(create_client=False)
            kernel_widget = console.shellwidgets[-1]
            self.connect(kernel_widget,
                      SIGNAL('create_ipython_client(QString)'),
                      lambda cf: self.connect_to_new_kernel(cf, kernel_widget))
    
    def connect_to_new_kernel(self, connection_file, kernel_widget):
        """
        After a new kernel is created, execute this action to connect the new
        kernel to the old client
        """
        console = self.main.extconsole
        shellwidget = self.tabwidget.currentWidget()
        
        # Close old kernel tab
        idx = console.get_shell_index_from_id(shellwidget.kernel_widget_id)
        console.close_console(index=idx, from_ipython_client=True)
        
        # Set attributes for the new kernel
        console.set_ipython_kernel_attrs(connection_file, kernel_widget)
        
        # Connect client to new kernel
        kernel_manager = self.ipython_app.create_kernel_manager(connection_file)        
        shellwidget.ipython_widget.kernel_manager = kernel_manager
        shellwidget.kernel_widget_id = id(kernel_widget)
        shellwidget.get_control().setFocus()
        
        # Rename client tab
        client_widget_id = id(shellwidget)
        self.rename_ipython_client_tab(connection_file, client_widget_id)
            
    #----Drag and drop
    #TODO: try and reimplement this block
    # (this is still the original code block copied from externalconsole.py)
#    def dragEnterEvent(self, event):
#        """Reimplement Qt method
#        Inform Qt about the types of data that the widget accepts"""
#        source = event.mimeData()
#        if source.hasUrls():
#            if mimedata2url(source):
#                pathlist = mimedata2url(source)
#                shellwidget = self.tabwidget.currentWidget()
#                if all([is_python_script(unicode(qstr)) for qstr in pathlist]):
#                    event.acceptProposedAction()
#                elif shellwidget is None or not shellwidget.is_running():
#                    event.ignore()
#                else:
#                    event.acceptProposedAction()
#            else:
#                event.ignore()
#        elif source.hasText():
#            event.acceptProposedAction()            
#            
#    def dropEvent(self, event):
#        """Reimplement Qt method
#        Unpack dropped data and handle it"""
#        source = event.mimeData()
#        shellwidget = self.tabwidget.currentWidget()
#        if source.hasText():
#            qstr = source.text()
#            if is_python_script(unicode(qstr)):
#                self.start(qstr)
#            elif shellwidget:
#                shellwidget.shell.insert_text(qstr)
#        elif source.hasUrls():
#            pathlist = mimedata2url(source)
#            if all([is_python_script(unicode(qstr)) for qstr in pathlist]):
#                for fname in pathlist:
#                    self.start(fname)
#            elif shellwidget:
#                shellwidget.shell.drop_pathlist(pathlist)
#        event.acceptProposedAction()
