"""

SUMMARY
------------------------------------------------------
Create a GUI (or even non-GUI) test directly on top of a running vm.

Copyright: Intra2net AG


CONTENTS
------------------------------------------------------
The following test generates a GUI panel to control a vm or
a set of vms.

At the present it must be used in conjunction with a normal
VNC client from which to interact with the vm's GUI.

The panel can be used to pause, resume and capture a vm as
well as for other neat purposes.

.. seealso:: Extra guide on GUI test development in the wiki.


INTERFACE
------------------------------------------------------

"""

import sys
from PyQt4 import QtGui
import logging

# custom imports
from multi_gui_utils import GUITestGenerator


log = logging.getLogger('avocado.test.log')


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
    log.info("Initiating the GUI test generator's GUI")
    app = QtGui.QApplication([])

    vmnet = env.get_vmnet()
    mt = GUITestGenerator(vmnet)
    mt.show()

    log.info("GUI test generator's GUI initiated")
    # TODO: Once this is converted from pseudotest to an actual tool,
    # we will be free to do this
    #sys.exit(app.exec_())
    app.exec_()
