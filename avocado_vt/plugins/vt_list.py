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
from avocado.core.settings import settings
from avocado.plugins.base import CLI

from ..loader import VirtTestLoader


# The original virt-test runner supports using autotest from a git checkout,
# so we'll have to support that as well. The code below will pick up the
# environment variable $AUTOTEST_PATH and do the import magic needed to make
# the autotest library available in the system.
AUTOTEST_PATH = None

if 'AUTOTEST_PATH' in os.environ:
    AUTOTEST_PATH = os.path.expanduser(os.environ['AUTOTEST_PATH'])
    client_dir = os.path.join(os.path.abspath(AUTOTEST_PATH), 'client')
    setup_modules_path = os.path.join(client_dir, 'setup_modules.py')
    if not os.path.exists(setup_modules_path):
        raise EnvironmentError("Although AUTOTEST_PATH has been declared, "
                               "%s missing." % setup_modules_path)
    import imp
    setup_modules = imp.load_source('autotest_setup_modules',
                                    setup_modules_path)
    setup_modules.setup(base_path=client_dir,
                        root_module_name="autotest.client")

# The code below is used by this plugin to find the virt test directory,
# so that it can load the virttest python lib, used by the plugin code.
# If the user doesn't provide the proper configuration, the plugin will
# fail to load.
VIRT_TEST_PATH = None

if 'VIRT_TEST_PATH' in os.environ:
    VIRT_TEST_PATH = os.environ['VIRT_TEST_PATH']
else:
    VIRT_TEST_PATH = settings.get_value(section='virt_test',
                                        key='virt_test_path', default=None)

if VIRT_TEST_PATH is not None:
    sys.path.append(os.path.expanduser(VIRT_TEST_PATH))

from virttest.standalone_test import SUPPORTED_TEST_TYPES
from virttest import defaults
from virttest import data_dir


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
        vt_compat_group_lister.add_argument("--vt-type", action="store",
                                            dest="vt_type",
                                            help="Choose test type (%s). "
                                                 "Default: qemu" %
                                            ", ".join(SUPPORTED_TEST_TYPES),
                                            default='qemu')
        vt_compat_group_lister.add_argument("--vt-guest-os", action="store",
                                            dest="vt_guest_os",
                                            default=None,
                                            help=("Select the guest OS to be "
                                                  "used (different guests "
                                                  "support different test "
                                                  "lists). You can list "
                                                  "available guests "
                                                  "with --vt-list-guests. "
                                                  "Default: %s" %
                                                  defaults.DEFAULT_GUEST_OS))
        vt_compat_group_lister.add_argument("--vt-list-guests",
                                            action="store_true",
                                            default=False,
                                            help="List available guests")
        machine = settings.get_value('vt.common', 'machine_type',
                                     default=defaults.DEFAULT_MACHINE_TYPE)
        vt_compat_group_lister.add_argument("--vt-machine-type",
                                            help="Choose the VM machine type. "
                                            "Default: %s" % machine,
                                            default=machine)
        vt_compat_group_lister.add_argument("--vt-only-filter", action="store",
                                            dest="vt_only_filter", default="",
                                            help=("List of space separated "
                                                  "'only' filters to be passed"
                                                  " to the config parser. "
                                                  " Default: ''"))

    def run(self, args):
        loader.register_plugin(VirtTestLoader)
