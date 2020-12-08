# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#
# See LICENSE for more details.
#
# Copyright: Red Hat Inc. 2015
# Author: Lucas Meneghel Rodrigues <lmr@redhat.com>

"""
Avocado plugin that augments 'avocado list' with avocado-virt related options.
"""

import os
import sys

from avocado.core.loader import loader
from avocado.core.plugin_interfaces import CLI

from virttest.compat import get_settings_value, add_option
from .vt import add_basic_vt_options, add_qemu_bin_vt_option
from ..loader import VirtTestLoader


# The original virt-test runner supports using autotest from a git checkout,
# so we'll have to support that as well. The code below will pick up the
# environment variable $AUTOTEST_PATH and do the import magic needed to make
# the autotest library available in the system.
AUTOTEST_PATH = None

if 'AUTOTEST_PATH' in os.environ:
    AUTOTEST_PATH = os.path.expanduser(os.environ['AUTOTEST_PATH'])
    CLIENT_DIR = os.path.join(os.path.abspath(AUTOTEST_PATH), 'client')
    SETUP_MODULES_PATH = os.path.join(CLIENT_DIR, 'setup_modules.py')
    if not os.path.exists(SETUP_MODULES_PATH):
        raise EnvironmentError("Although AUTOTEST_PATH has been declared, "
                               "%s missing." % SETUP_MODULES_PATH)
    import imp
    SETUP_MODULES = imp.load_source('autotest_setup_modules',
                                    SETUP_MODULES_PATH)
    SETUP_MODULES.setup(base_path=CLIENT_DIR,
                        root_module_name="autotest.client")

# The code below is used by this plugin to find the virt test directory,
# so that it can load the virttest python lib, used by the plugin code.
# If the user doesn't provide the proper configuration, the plugin will
# fail to load.
VIRT_TEST_PATH = None

if 'VIRT_TEST_PATH' in os.environ:
    VIRT_TEST_PATH = os.environ['VIRT_TEST_PATH']
else:
    VIRT_TEST_PATH = get_settings_value(section='virt_test',
                                        key='virt_test_path', default=None)

if VIRT_TEST_PATH is not None:
    sys.path.append(os.path.expanduser(VIRT_TEST_PATH))

from virttest import data_dir   # pylint: disable=C0413


_PROVIDERS_DOWNLOAD_DIR = os.path.join(data_dir.get_test_providers_dir(),
                                       'downloads')

try:
    assert len(os.listdir(_PROVIDERS_DOWNLOAD_DIR)) != 0
except (OSError, AssertionError):
    raise EnvironmentError("Bootstrap missing. "
                           "Execute 'avocado vt-bootstrap' or disable this "
                           "plugin to get rid of this message")


class VTLister(CLI):

    """
    Avocado VT - implements legacy virt-test listing
    """

    name = 'vt-list'
    description = "Avocado-VT/virt-test support for 'list' command"

    def configure(self, parser):
        """
        Add the subparser for the run action.

        :param parser: Main test runner parser.
        """
        list_subcommand_parser = parser.subcommands.choices.get('list', None)
        if list_subcommand_parser is None:
            return

        vt_compat_group_lister = list_subcommand_parser.add_argument_group(
            'Virt-Test compat layer - Lister options')

        help_msg = ("Also list the available guests (this option ignores the "
                    "--vt-config and --vt-guest-os)")
        add_option(parser=vt_compat_group_lister,
                   dest='vt.list_guests',
                   arg='--vt-list-guests',
                   action='store_true',
                   default=False,
                   help=help_msg)

        help_msg = ("Also list the available arch/machines for the given guest"
                    " OS. (Use \"--vt-guest-os ''\" to see all combinations; "
                    "--vt-config --vt-machine-type and --vt-arch args are "
                    "ignored)")
        add_option(parser=vt_compat_group_lister,
                   dest='vt.list_archs',
                   arg='--vt-list-archs',
                   action='store_true',
                   default=False,
                   help=help_msg)

        add_basic_vt_options(vt_compat_group_lister)
        add_qemu_bin_vt_option(vt_compat_group_lister)

    def run(self, config):
        loader.register_plugin(VirtTestLoader)
