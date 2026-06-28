"""

SUMMARY
------------------------------------------------------
Test to experiment with the multi-GUI virtual user extensions.

Copyright: Intra2net AG


CONTENTS
------------------------------------------------------
In particular, we might run it on manually prepared vm4/vm5 whose
preparation involves opening and maximizing paint/KolourPaint as
a window (mouse testing) and repeating the same with another window
for an editor (notepad/Kwrite). The preparation of the vms is concluded
with a stored online state with the name of "vu_alt".

Once you have prepared or obtained such images, you can both get the
"vu_alt" state and run the test with::

    sh run.sh setup=develop mode=testbed vms=vm4,vm5

Then experiment on a canvas (paint->mouse) or blank space (editor->keys).


INTERFACE
------------------------------------------------------

"""

import sys
import random
from PyQt4 import QtGui, QtCore
import logging

# custom imports
from multi_gui_utils import GUITestGenerator, Windows, Linux


log = logging.getLogger('avocado.test.log')


###############################################################################
# TESTING
###############################################################################


def stress_test(gui, name, *args):
    """
    Run a stress test of a given class by calling this function.

    :param gui: the GUI control window
    :type gui: GUITestGenerator object
    :param str name: test class :"mouse-grid", "mouse-hit", "all-keys", or "custom"
    :param args: test arguments
    """
    gui.interrupted = False

    def interrupt():
        gui.interrupted = True
        gui.button_run.setText("Stopping")
        log.info("Interrupting current stress test run")

    def interrupted():
        gui.button_run.setText("Run")
        gui.disconnect(gui.button_run, QtCore.SIGNAL('clicked()'), interrupt)
        gui.connect(gui.button_run, QtCore.SIGNAL('clicked()'), gui.run)
        if gui.interrupted:
            log.info("Current stress test interrupted")
            gui.interrupted = False
        else:
            log.info("Current stress test completed")

    gui.button_run.setText("Stop")
    gui.disconnect(gui.button_run, QtCore.SIGNAL('clicked()'), gui.run)
    gui.connect(gui.button_run, QtCore.SIGNAL('clicked()'), interrupt)

    if name == "mouse-grid":
        gui.worker = StressTestMouseGrid(gui, *args)
    elif name == "mouse-hit":
        gui.worker = StressTestMouseHit(gui, *args)
    elif name == "all-keys":
        gui.worker = StressTestAllKeys(gui, *args)
    elif name == "custom":
        gui.worker = StressTestCustom(gui, *args)
    gui.worker.finished.connect(interrupted)
    gui.worker.start()


class StressTestMouseGrid(QtCore.QThread):
    """
    Fill a grid by clicks resulting in a filled square
    in case of 100% mouse hover+click precision.

    Window to use: **paint**

    Tested functionality: **mouse**
    """
    def __init__(self, gui, step=10):
        """
        Construct the stress test.

        :param gui: the GUI control window
        :type gui: GUITestGenerator object
        :param int step: grid interval
        """
        QtCore.QThread.__init__(self)
        self.gui = gui
        self.step = step

    def run(self):
        """Run the stress test."""
        from guibot.guibot.location import Location
        l = Location(0, 0)
        for i in range(0, 500/self.step):
            l.xpos = 100 + self.step * i
            for j in range(0, 500/self.step):
                l.ypos = 100 + self.step * j
                self.gui.user.click(l)
                if self.gui.interrupted:
                    return


class StressTestMouseHit(QtCore.QThread):
    """
    Test mouse precision by clicking on the same location
    then hovering away and then clicking again resulting
    in a single point visible on the screen in the case
    of 100% mouse hover+click precision.

    Window to use: **paint**

    Tested functionality: **mouse**
    """
    def __init__(self, gui, trials=100):
        """
        Construct the stress test.

        :param gui: the GUI control window
        :type gui: GUITestGenerator object
        :param int trials: number of trials to hit target
        """
        QtCore.QThread.__init__(self)
        self.gui = gui
        self.trials = trials

    def run(self):
        """Run the stress test."""
        from guibot.guibot.location import Location
        l = Location(100, 100)
        for i in range(self.trials):
            log.info(f"Performing hover-click hit {i}")
            l.xpos = random.randrange(100, 500)
            l.ypos = random.randrange(100, 500)
            self.gui.user.hover(l)
            l.xpos = 300
            l.ypos = 300
            self.gui.user.click(l)
            if self.gui.interrupted:
                return


class StressTestAllKeys(QtCore.QThread):
    """
    Type all printable keys to check if the key translation
    is correct for the current virtual user backend.

    Window to use: **editor**

    Tested functionality: **keyboard**
    """
    def __init__(self, gui):
        """
        Construct the stress test.

        :param gui: the GUI control window
        :type gui: GUITestGenerator object
        """
        QtCore.QThread.__init__(self)
        self.gui = gui

    def run(self):
        """Run the stress test."""
        self.gui.user.type_text("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
        self.gui.user.press_keys([self.gui.user.ENTER])
        if self.gui.interrupted:
            return
        self.gui.user.type_text("`1234567890-=~!@#$%^&*()_+")
        self.gui.user.press_keys([self.gui.user.ENTER])
        if self.gui.interrupted:
            return
        self.gui.user.type_text("[]{};'\\:\"|,./<>?")
        self.gui.user.press_keys([self.gui.user.ENTER])


class StressTestCustom(QtCore.QThread):
    """
    Perform a custom stress test. The only thing you need to
    do is put your code in the :py:func:`StressTestCustom.run`
    method, allowing it to be interruptible at certain places
    through lines like::

        if self.gui.interrupted:
            return

    Window to use: **paint, editor, etc.**

    Tested functionality: **mouse, keyboard, GUI control, etc.**
    """
    def __init__(self, gui, visual_os="windows"):
        """
        Construct the stress test.

        :param gui: the GUI control window
        :type gui: GUITestGenerator object
        """
        QtCore.QThread.__init__(self)
        self.gui = gui
        self.visual_os = visual_os

    def run(self):
        """
        Run the stress test.

        This code is just an example where we open the Windows menu
        500 times waiting for a failure to do so. It can be customized
        or changed to any other desired behavior.
        """
        if self.visual_os == "windows":
            os_type = Windows
        elif self.visual_os == "linux":
            os_type = Linux
        else:
            raise ValueError("Inappropriate choice of OS for custom stress test")
        os = os_type(self.gui.image_root, dc=self.gui.user.dc_backend)
        # NOTE: this could be moved to the arguments but is kept here
        # to simplify the example stress test
        n = 500
        for i in range(n):
            log.info(f"Attempt {i}\{n}")
            os.start_menu_option()
            os.press_keys(os.ESC)
            if self.gui.interrupted:
                return
        log.info("No errors")


###############################################################################
# TEST MAIN
###############################################################################

def run(test, params, env):
    """
    Main test run.

    :param test: test object
    :type test: :py:class:`avocado_vt.test.VirtTest`
    :param params: extended dictionary of parameters
    :type params: :py:class:`virttest.utils_params.Params`
    :param env: environment object
    :type env: :py:class:`virttest.utils_env.Env`
    """
    log.info("Initiating the GUI test generator's GUI with all stress tests")
    app = QtGui.QApplication([])

    vmnet = env.get_vmnet()
    mt = GUITestGenerator(vmnet)
    mt.show()
    mt.text_edit.setText("self.stress_test(self, 'mouse-grid', 10)\u2029"
                         "self.stress_test(self, 'mouse-hit', 100)\u2029"
                         "self.stress_test(self, 'all-keys')\u2029"
                         "self.stress_test(self, 'custom')\u2029")
    mt.stress_test = stress_test

    log.info("GUI test generator's GUI initiated")
    # TODO: Once this is converted from pseudotest to an actual tool,
    # we will be free to do this
    #sys.exit(app.exec_())
    app.exec_()

    log.info("Testbed completed successfully!")
