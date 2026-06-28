"""

SUMMARY
------------------------------------------------------
Utility shared among the multi-GUI tests.

Copyright: Intra2net AG

...todo:: Try to liberate the virtual machine environment
          again in order to turn this utility into a proper
          tool together with the two multi_gui pseudotests.


INTERFACE
------------------------------------------------------

"""

import re
import os
import logging
# TODO: migrate from logging to log usage in messages
log = logging = logging.getLogger('avocado.test.utils')

from PyQt4 import QtGui, QtCore

from avocado.utils import process
from avocado.core.settings import settings

from avocado_i2n.states import setup as ss

# virtual user backend has to be available in order to use these tools at all
from guibot.guibot import GuiBot
from guibot.config import GlobalConfig
from guibot.controller import VNCDoToolController


class GUITestGenerator(QtGui.QWidget):
    """Test generator class."""

    def __init__(self, vmnet, parent=None):
        """
        Construct the main control window of the GUI test generator.

        :param vmnet: network of available vms
        :type vmnet: :py:class:`avocado_i2n.vmnet.network.VMNetwork`
        :param parent: parent widget
        :type parent: :py:class:`QWidget`
        """
        QtGui.QWidget.__init__(self, parent)

        # these are set for documentation purposes
        self.screen = None
        self.user = None
        self.vm = None

        self.vmnet, self.path = vmnet, vmnet.test.logdir
        self.test, self.params, self.env = vmnet.test, vmnet.params, vmnet.env
        self.image_root = os.path.join(vmnet.params["suite_path"], "data", "visual")
        if self.params.get("store_permanently", "no") == "yes":
            self.path = self.image_root
            logging.info("Storing all captured screens and executed code permanently in %s",
                         self.path)
        else:
            logging.info("Storing all captured screens and executed code until rerun in %s",
                         self.path)
        self.paused = False

        self.setWindowTitle('GUI Test Generator')

        font_family = 'Helvetica'
        font_size = 10

        self.line_dump = QtGui.QLineEdit("000.png")
        self.line_dump.setFixedSize(100, 20)
        self.line_dump.setInputMask('999.aaa')

        self.button_capture = QtGui.QPushButton("Capture")
        self.button_capture.setFixedSize(100, 20)
        self.button_capture.setStyleSheet('QPushButton { font-family: ' + font_family + '; font-size: ' + str(font_size) + 't; }')
        self.connect(self.button_capture, QtCore.SIGNAL('clicked()'), self.capture)

        self.button_pause = QtGui.QPushButton("Pause")
        self.button_pause.setFixedSize(100, 20)
        self.button_pause.setStyleSheet('QPushButton { font-family: ' + font_family + '; font-size: ' + str(font_size) + 't; }')
        self.connect(self.button_pause, QtCore.SIGNAL('clicked()'), self.pause)

        self.button_resume = QtGui.QPushButton("Resume")
        self.button_resume.setFixedSize(100, 20)
        self.button_resume.setStyleSheet('QPushButton { font-family: ' + font_family + '; font-size: ' + str(font_size) + 't; }')
        self.connect(self.button_resume, QtCore.SIGNAL('clicked()'), self.resume)
        self.button_resume.setEnabled(False)

        self.line_state = QtGui.QLineEdit("current_state")
        self.line_state.setFixedSize(100, 20)

        self.button_state = QtGui.QPushButton("Store")
        self.button_state.setFixedSize(100, 20)
        self.button_state.setStyleSheet('QPushButton { font-family: ' + font_family + '; font-size: ' + str(font_size) + 't; }')
        self.connect(self.button_state, QtCore.SIGNAL('clicked()'), self.store)

        self.list_view = QtGui.QListWidget()
        self.list_view.setFixedWidth(200)
        self.list_view.setFont(QtGui.QFont(font_family, font_size))
        self.connect(self.list_view, QtCore.SIGNAL("itemDoubleClicked (QListWidgetItem *)"), self.retrieve)
        self.list_view.setContextMenuPolicy(QtCore.Qt.ActionsContextMenu)
        # retrieve option in the context menu
        retrieve_action = QtGui.QAction("Retrieve", self)
        retrieve_action.setFont(QtGui.QFont(font_family, font_size))
        self.list_view.addAction(retrieve_action)
        retrieve_action.triggered.connect(self.retrieve)
        # remove option in the context menu
        remove_action = QtGui.QAction("Remove", self)
        remove_action.setFont(QtGui.QFont(font_family, font_size))
        self.list_view.addAction(remove_action)
        remove_action.triggered.connect(self.remove)

        self.text_edit = QtGui.QTextEdit()
        code_file = os.path.join(self.path, "gui.control")
        if os.path.exists(code_file):
            with open(code_file) as f:
                code = f.read()
                paragraphs = code.replace('\n', '\u2029')
        else:
            paragraphs = str("gui.user.type_text(\"hello world\")\u2029"
                             "linux = get_vo(\"linux\")\u2029"
                             "linux.start_menu_option(\"firefox\")\u2029")
        self.text_edit.setPlainText(paragraphs)
        cursor = self.text_edit.textCursor()
        cursor.setPosition(0)
        cursor.setPosition(0 if os.path.exists(code_file) else 33, QtGui.QTextCursor.KeepAnchor)
        self.text_edit.setTextCursor(cursor)
        self.text_edit.setAcceptDrops(True)

        self.button_run = QtGui.QPushButton("Run")
        self.button_run.setFixedSize(100, 20)
        self.button_run.setStyleSheet('QPushButton { font-family: ' + font_family + '; font-size: ' + str(font_size) + 't; }')
        self.connect(self.button_run, QtCore.SIGNAL('clicked()'), self.run)

        self.combo_box = QtGui.QComboBox()
        self.combo_box.setFixedSize(100, 20)
        for vm in vmnet.get_ordered_vms():
            vnc_port = vm.vnc_port - 5900
            self.combo_box.addItem("%s :%s" % (vm.name, vnc_port))
        self.combo_box.currentIndexChanged[str].connect(self.switch)

        # set current vm screen
        self.switch()

        hbox1 = QtGui.QHBoxLayout()
        hbox1.addWidget(self.line_dump)
        hbox1.addWidget(self.button_capture)

        hbox2 = QtGui.QHBoxLayout()
        hbox2.addWidget(self.button_pause)
        hbox2.addWidget(self.button_resume)

        hbox3 = QtGui.QHBoxLayout()
        hbox3.addWidget(self.line_state)
        hbox3.addWidget(self.button_state)

        vbox1 = QtGui.QVBoxLayout()
        vbox1.addLayout(hbox1)
        vbox1.addLayout(hbox2)
        vbox1.addLayout(hbox3)
        vbox1.addWidget(self.list_view, 1)
        vbox1.setAlignment(QtCore.Qt.AlignTop)

        hbox4 = QtGui.QHBoxLayout()
        hbox4.addWidget(self.button_run)
        hbox4.addStretch(1)
        hbox4.addWidget(self.combo_box)

        vbox2 = QtGui.QVBoxLayout()
        vbox2.addWidget(self.text_edit, 1)
        vbox2.addLayout(hbox4)

        hbox5 = QtGui.QHBoxLayout()
        hbox5.addLayout(vbox1)
        hbox5.addLayout(vbox2)

        self.setLayout(hbox5)

        QtGui.QApplication.setStyle(QtGui.QStyleFactory.create('cleanlooks'))

    def disable(self):
        """Disable all buttons."""
        self.button_capture.setEnabled(False)
        # remember whether the vm is paused
        self.paused = not self.button_pause.isEnabled()
        self.button_pause.setEnabled(False)
        self.button_resume.setEnabled(False)
        self.button_run.setEnabled(False)
        self.button_state.setEnabled(False)
        self.list_view.setEnabled(False)
        self.combo_box.setEnabled(False)

    def enable(self):
        """Enable all buttons."""
        self.button_capture.setEnabled(True)
        if self.paused:
            self.button_pause.setEnabled(False)
            self.button_resume.setEnabled(True)
        else:
            self.button_pause.setEnabled(True)
            self.button_resume.setEnabled(False)
        self.button_run.setEnabled(True)
        self.button_state.setEnabled(True)
        self.list_view.setEnabled(True)
        self.combo_box.setEnabled(True)

    def capture(self):
        """Capture a screenshot of the current vm into a file."""
        filename = str(self.line_dump.text())
        filepath = os.path.join(self.path, filename)
        self.user.dc_backend.capture_screen().save(filepath)
        if self.vm.params["capture_autoopen"] == "yes":
            process.run("%s %s" % (self.vm.params["capture_autoopen_editor"], filepath))
        filenum = re.match(".*(\d\d\d)\..*", filename).group(1)
        filename = filename.replace(filenum, "%03d" % (int(filenum)+1))
        self.line_dump.setText(filename)

    def pause(self):
        """Pause the current vm if it is running."""
        self.vm.pause()
        self.button_pause.setEnabled(False)
        self.button_resume.setEnabled(True)

    def resume(self):
        """Resume the current vm if it is paused."""
        self.vm.resume()
        self.button_resume.setEnabled(False)
        self.button_pause.setEnabled(True)

    def store(self):
        """Store the state of the current vm as an on state."""
        self.button_state.setText("Storing")
        self.disable()

        def store_done():
            if len(self.list_view.findItems(self.vm.params["set_state"], QtCore.Qt.MatchExactly)) == 0:
                self.list_view.addItem(self.vm.params["set_state"])
            self.button_state.setText("Store")
            self.enable()

        self.worker = StoreThread(self)
        self.worker.finished.connect(store_done)
        self.worker.start()

    def retrieve(self):
        """Retrieve a state of the current vm as an on state."""
        self.button_state.setText("Retrieving")
        self.disable()

        def retrieve_done():
            self.button_state.setText("Store")
            self.enable()

        self.worker = RetrieveThread(self)
        self.worker.finished.connect(retrieve_done)
        self.worker.start()

    def remove(self):
        """Remove a state of the current vm as an on state."""
        self.button_state.setText("Removing")
        self.disable()

        def remove_done():
            self.button_state.setText("Store")
            self.enable()

        self.worker = RemoveThread(self)
        self.worker.finished.connect(remove_done)
        self.worker.start()

    def run(self):
        """Run highlighted visual user code on the current vm."""
        logging.info("Running selected visual code")
        logging.info("----------------------------")
        self.button_run.setText("Running")
        self.disable()

        def run_done():
            logging.info("---------------------------------")
            logging.info("Done running selected visual code")
            self.button_run.setText("Run")
            self.enable()

        self.worker = RunThread(self)
        self.worker.finished.connect(run_done)
        self.worker.start()

    def switch(self):
        """Switch the current vm with another one from a list."""
        logging.info("Switching the platform and screen to %s", self.combo_box.currentText())
        self.button_run.setText("Switching")
        self.disable()

        def switch_done():
            self.button_run.setText("Run")
            self.enable()

        self.worker = SwitchThread(self)
        self.worker.finished.connect(switch_done)
        self.worker.start()

    def closeEvent(self, event):
        reply = QtGui.QMessageBox.question(self, "Save work",
                                           "Do you want to save any changes you have made?",
                                           QtGui.QMessageBox.Yes | QtGui.QMessageBox.No,
                                           QtGui.QMessageBox.Yes)
        if reply == QtGui.QMessageBox.Yes:
            control_file = os.path.join(self.path, "gui.control")
            with open(control_file, "w") as f:
                paragraphs = str(self.text_edit.toPlainText())
                code = paragraphs.replace('\u2029', '\n')
                f.write(code)

        QtGui.QWidget.closeEvent(self, event)


class StoreThread(QtCore.QThread):
    """A thread for storing a vm state."""

    def __init__(self, gui):
        """
        Construct the thread.

        :param gui: the GUI control window
        :type gui: GUITestGenerator object
        """
        QtCore.QThread.__init__(self)
        self.gui = gui

    def run(self):
        """Run the thread."""
        self.gui.vm.params["vms"] = self.gui.vm.name
        self.gui.vm.params["set_state"] = self.gui.line_state.text()
        self.gui.vm.params["set_type"] = "on"
        self.gui.vm.params["set_mode"] = "ff"
        ss.set_states(self.gui.vm.params, self.gui.vmnet.env)


class RetrieveThread(QtCore.QThread):
    """A thread for retrieving a vm state."""

    def __init__(self, gui):
        """
        Construct the thread.

        :param gui: the GUI control window
        :type gui: GUITestGenerator object
        """
        QtCore.QThread.__init__(self)
        self.gui = gui

    def run(self):
        """Run the thread."""
        self.gui.vm.params["vms"] = self.gui.vm.name
        for item in self.gui.list_view.selectedItems():
            self.gui.vm.params["get_state"] = item.text()
            self.gui.vm.params["get_type"] = "on"
            self.gui.vm.params["get_mode"] = "ri"
            ss.get_states(self.gui.vm.params, self.gui.vmnet.env)


class RemoveThread(QtCore.QThread):
    """A thread for removing a vm state."""

    def __init__(self, gui):
        """
        Construct the thread.

        :param gui: the GUI control window
        :type gui: GUITestGenerator object
        """
        QtCore.QThread.__init__(self)
        self.gui = gui

    def run(self):
        """Run the thread."""
        self.gui.vm.params["vms"] = self.gui.vm.name
        for item in self.gui.list_view.selectedItems():
            self.gui.vm.params["unset_state"] = item.text()
            self.gui.vm.params["unset_type"] = "on"
            self.gui.vm.params["unset_mode"] = "fi"
            ss.unset_states(self.gui.vm.params, self.gui.vmnet.env)
            self.gui.list_view.takeItem(self.gui.list_view.row(item))


class RunThread(QtCore.QThread):
    """A thread for running visual code."""

    def __init__(self, gui):
        """
        Construct the thread.

        :param gui: the GUI control window
        :type gui: GUITestGenerator object
        """
        QtCore.QThread.__init__(self)
        self.gui = gui

    def run(self):
        """Run the thread."""
        control_file = os.path.join(self.gui.path, "gui.control")
        with open(control_file, "w") as f:
            paragraphs = str(self.gui.text_edit.textCursor().selectedText())
            code = paragraphs.replace('\u2029', '\n')
            logging.debug("Selected visual code:\n%s", code)
            f.write(code)

        # some shortcuts on the editor side
        gui = self.gui
        other_vos = {"linux": Linux, "windows": Windows}
        assert gui.user is not None, "Virtual user should be initialized"

        def get_vo(voname, *args, **kwargs):
            if voname in other_vos.keys():
                return other_vos[voname](gui.image_root, *args,
                                         dc=gui.user.dc_backend, **kwargs)
            else:
                return gui.user

        with open(control_file) as control_handle:
            code = compile(control_handle.read(), control_file, 'exec')
            try:
                exec(code)
            except Exception as e:
                logging.warning("Error during GUI code execution:\n%s", e)


class SwitchThread(QtCore.QThread):
    """A thread for switch a vm platform."""

    def __init__(self, gui):
        """
        Construct the thread.

        :param gui: the GUI control window
        :type gui: GUITestGenerator object
        """
        QtCore.QThread.__init__(self)
        self.gui = gui

    def run(self):
        """Run the thread."""
        vmname = str(re.match("^(\w+) :\d+", self.gui.combo_box.currentText()).group(1))
        self.gui.vm = self.gui.vmnet.nodes[vmname].platform

        # refresh the detected states
        self.gui.vm.params["vms"] = vmname
        self.gui.vm.params["check_type"] = "on"
        states = ss.show_states(self.gui.vm.params, self.gui.vmnet.env)
        self.gui.list_view.clear()
        self.gui.list_view.addItems(states)

        # each platform supports different logging verbosity
        lvl = self.gui.vm.params.get_numeric("vu_logging_level", 20)
        logging.getLogger("guibot").setLevel(lvl)
        GlobalConfig.image_logging_level = lvl
        GlobalConfig.image_logging_destination = os.path.join(self.gui.path, "imglogs")

        # initialize a desktop control backend for the selected vm
        dc = VNCDoToolControl(synchronize=False)
        # starting from 5900, i.e. :0 == 5900
        dc.params["vncdotool"]["vnc_port"] = self.gui.vm.vnc_port - 5900
        dc.params["vncdotool"]["vnc_delay"] = 0.02
        dc.synchronize_backend()
        logging.debug("Initiating vnc server screen for vm %s on port %s (%s)",
                      self.gui.vm.name, dc.params["vncdotool"]["vnc_port"],
                      self.gui.vm.vnc_port)
        self.gui.user = VisualObject(self.gui.image_root, dc=dc)
        self.gui.user.add_path(self.gui.path)


class VisualObject(GuiBot):
    """
    Visual objects contain logic for manipulation of visual
    information.
    """

    def image_root(self, r=None):
        """
        Image root location where the images for the visual
        object will be searched for.
        """
        if r is None:
            return self._image_root
        else:
            self._image_root = r

    def __init__(self, imgroot, dc=None, cv=None):
        """
        Construct a visual object with optional custom backends.

        :param str imgroot: the image root location for the object
        :param dc: desktop control backend
        :type dc: Controller object
        :param cv: computer vision backend
        :type cv: Finder object
        """
        super(VisualObject, self).__init__(dc=dc, cv=cv)
        self._image_root = imgroot
        self.add_path(self._image_root)


class Linux(VisualObject):
    """
    Visual object to handle Linux OS related
    operations on the GUI.
    """

    def start_menu_option(self, option="admin"):
        """
        Open an option in the start menu, opening the start
        menu if necessary.

        :param str option: option in the start menu
        """
        logging.info("Looking for '%s' in the start menu", option)
        self.press_keys([self.ALT, self.F2])
        self.type_text(option)
        self.press_keys(self.ENTER)


class Windows(VisualObject):
    """
    Visual object to handle Windows OS related
    operations on the GUI.
    """

    def start_menu_option(self, option="admin"):
        """
        Open an option in the start menu, opening the start
        menu if necessary.

        :param str option: option in the start menu
        """
        logging.info("Looking for '%s' in the start menu", option)
        self.click("win10-start-button")
        self.type_text(option)
        self.press_keys(self.ENTER)
