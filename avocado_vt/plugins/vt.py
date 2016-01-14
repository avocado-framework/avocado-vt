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
Avocado VT plugin
"""

import os

from avocado.core.loader import loader
from avocado.core.settings import settings
from avocado.utils import path as utils_path
from avocado.plugins.base import CLI

from virttest import data_dir
from virttest import defaults
from virttest import standalone_test
from virttest.standalone_test import SUPPORTED_TEST_TYPES
from virttest.standalone_test import SUPPORTED_LIBVIRT_URIS
from virttest.standalone_test import SUPPORTED_NET_TYPES

from ..loader import VirtTestLoader


_PROVIDERS_DOWNLOAD_DIR = os.path.join(data_dir.get_test_providers_dir(),
                                       'downloads')
try:
    assert len(os.listdir(_PROVIDERS_DOWNLOAD_DIR)) != 0
except (OSError, AssertionError):
    raise EnvironmentError("Bootstrap missing. "
                           "Execute 'avocado vt-bootstrap' or disable this "
                           "plugin to get rid of this message")


class VTRun(CLI):

    """
    Avocado VT - legacy virt-test support
    """

    name = 'vt'
    description = "Avocado VT/virt-test support to 'run' command"

    def configure(self, parser):
        """
        Add the subparser for the run action.

        :param parser: Main test runner parser.
        """
        def str_or_none(arg):
            if arg is None:
                return "Could not find one"
            else:
                return arg
        run_subcommand_parser = parser.subcommands.choices.get('run', None)
        if run_subcommand_parser is None:
            return

        try:
            qemu_bin_path = standalone_test.find_default_qemu_paths()[0]
        except (RuntimeError, utils_path.CmdNotFoundError):
            qemu_bin_path = None

        qemu_nw_msg = "QEMU network option (%s). " % ", ".join(
            SUPPORTED_NET_TYPES)
        qemu_nw_msg += "Default: user"

        vt_compat_group_setup = run_subcommand_parser.add_argument_group(
            'Virt-Test compat layer - VM Setup options')
        vt_compat_group_common = run_subcommand_parser.add_argument_group(
            'Virt-Test compat layer - Common options')
        vt_compat_group_qemu = run_subcommand_parser.add_argument_group(
            'Virt-Test compat layer - QEMU options')
        vt_compat_group_libvirt = run_subcommand_parser.add_argument_group(
            'Virt-Test compat layer - Libvirt options')

        vt_compat_group_common.add_argument("--vt-config", action="store",
                                            dest="vt_config",
                                            help=("Explicitly choose a "
                                                  "cartesian config. "
                                                  "When choosing this, "
                                                  "some options will be "
                                                  "ignored (see options "
                                                  "below)"))
        vt_compat_group_common.add_argument("--vt-type", action="store",
                                            dest="vt_type",
                                            help=("Choose test type (%s). "
                                                  "Default: qemu" %
                                                  ", ".join(
                                                      SUPPORTED_TEST_TYPES)),
                                            default='qemu')
        arch = settings.get_value('vt.common', 'arch', default=None)
        vt_compat_group_common.add_argument("--vt-arch",
                                            help="Choose the VM architecture. "
                                            "Default: %s" % arch,
                                            default=arch)
        machine = settings.get_value('vt.common', 'machine_type',
                                     default=defaults.DEFAULT_MACHINE_TYPE)
        vt_compat_group_common.add_argument("--vt-machine-type",
                                            help="Choose the VM machine type. "
                                            "Default: %s" % machine,
                                            default=machine)
        vt_compat_group_common.add_argument("--vt-guest-os", action="store",
                                            dest="vt_guest_os",
                                            default=defaults.DEFAULT_GUEST_OS,
                                            help=("Select the guest OS to "
                                                  "be used. If --vt-config is "
                                                  "provided, this will be "
                                                  "ignored. Default: %s" %
                                                  defaults.DEFAULT_GUEST_OS))
        vt_compat_group_common.add_argument("--vt-no-filter", action="store",
                                            dest="vt_no_filter", default="",
                                            help=("List of space separated "
                                                  "'no' filters to be passed "
                                                  "to the config parser. "
                                                  "If --vt-config is "
                                                  "provided, this will be "
                                                  "ignored. Default: ''"))
        qemu_bin = settings.get_value('vt.qemu', 'qemu_bin',
                                      default=qemu_bin_path)
        vt_compat_group_qemu.add_argument("--vt-qemu-bin", action="store",
                                          dest="vt_qemu_bin",
                                          default=qemu_bin,
                                          help=("Path to a custom qemu binary "
                                                "to be tested. If --vt-config "
                                                "is provided and this flag is "
                                                "omitted, no attempt to set "
                                                "the qemu binaries will be "
                                                "made. Current: %s" %
                                                str_or_none(qemu_bin)))
        qemu_dst = settings.get_value('vt.qemu', 'qemu_dst_bin',
                                      default=qemu_bin_path)
        vt_compat_group_qemu.add_argument("--vt-qemu-dst-bin", action="store",
                                          dest="vt_dst_qemu_bin",
                                          default=qemu_dst,
                                          help=("Path to a custom qemu binary "
                                                "to be tested for the "
                                                "destination of a migration, "
                                                "overrides --vt-qemu-bin. "
                                                "If --vt-config is provided "
                                                "and this flag is omitted, "
                                                "no attempt to set the qemu "
                                                "binaries will be made. "
                                                "Current: %s" %
                                                str_or_none(qemu_dst)))
        vt_compat_group_qemu.add_argument("--vt-extra-params", nargs='*',
                                          help="List of 'key=value' pairs "
                                          "passed to cartesian parser.")
        supported_uris = ", ".join(SUPPORTED_LIBVIRT_URIS)
        uri_current = settings.get_value('vt.libvirt', 'connect_uri',
                                         default=None)
        vt_compat_group_libvirt.add_argument("--vt-connect-uri",
                                             action="store",
                                             dest="vt_connect_uri",
                                             default=uri_current,
                                             help=("Choose test connect uri "
                                                   "for libvirt (E.g: %s). "
                                                   "Current: %s" %
                                                   (supported_uris,
                                                    uri_current)))

    def run(self, args):
        """
        Run test modules or simple tests.

        :param args: Command line args received from the run subparser.
        """
        loader.register_plugin(VirtTestLoader)
