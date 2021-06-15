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
from avocado.core.plugin_interfaces import CLI
from avocado.utils import path as utils_path

from virttest import data_dir, defaults, standalone_test
from virttest.compat import get_settings_value, add_option
from virttest.standalone_test import (SUPPORTED_LIBVIRT_URIS,
                                      SUPPORTED_TEST_TYPES)

from ..loader import VirtTestLoader


_PROVIDERS_DOWNLOAD_DIR = os.path.join(data_dir.get_test_providers_dir(),
                                       'downloads')
try:
    assert len(os.listdir(_PROVIDERS_DOWNLOAD_DIR)) != 0
except (OSError, AssertionError):
    raise ImportError("Bootstrap missing. "
                      "Execute 'avocado vt-bootstrap' or disable this "
                      "plugin to get rid of this message")


def add_basic_vt_options(parser):
    """
    Add basic vt options to parser
    """

    help_msg = ("Explicitly choose a cartesian config. When choosing this, "
                "some options will be ignored (see options below)")
    add_option(parser,
               dest='vt.config',
               arg='--vt-config',
               help=help_msg)

    help_msg = "Save the resulting cartesian config to a file"
    add_option(parser,
               dest='vt.save_config',
               arg='--vt-save-config',
               help=help_msg)

    help_msg = "Enable short names as test names when using a config file"
    add_option(parser,
               dest='vt.short_names_when_config',
               arg='--vt-short-names-when-config',
               help=help_msg)

    help_msg = ("Choose test type (%s). Default: %%(default)s" %
                ", ".join(SUPPORTED_TEST_TYPES))
    add_option(parser,
               dest='vt.type',
               arg='--vt-type',
               default=SUPPORTED_TEST_TYPES[0],
               help=help_msg)

    arch = get_settings_value('vt.common', 'arch', default=None)
    help_msg = "Choose the VM architecture. Default: %(default)s"
    add_option(parser,
               dest='vt.common.arch',
               arg='--vt-arch',
               default=arch,
               help=help_msg)

    machine = get_settings_value('vt.common', 'machine_type',
                                 default=defaults.DEFAULT_MACHINE_TYPE)
    help_msg = "Choose the VM machine type. Default: %(default)s"
    add_option(parser,
               dest='vt.common.machine_type',
               arg='--vt-machine-type',
               default=machine,
               help=help_msg)

    help_msg = ("Select the guest OS to be used. If --vt-config is provided, "
                "this will be ignored. Default: %(default)s")
    add_option(parser,
               dest='vt.guest_os',
               arg='--vt-guest-os',
               default=defaults.DEFAULT_GUEST_OS,
               help=help_msg)

    help_msg = ("List of space separated 'no' filters to be passed to the "
                "config parser.  Default: '%(default)s'")
    add_option(parser,
               dest='vt.no_filter',
               arg='--vt-no-filter',
               default="",
               help=help_msg)

    help_msg = ("List of space separated 'only' filters to be passed to the "
                "config parser.  Default: '%(default)s'")
    add_option(parser,
               dest='vt.only_filter',
               arg='--vt-only-filter',
               default="",
               help=help_msg)

    help_msg = ("Allows to selectively skip certain default filters. This uses "
                "directly 'tests-shared.cfg' and instead of "
                "'$provider/tests.cfg' and applies following lists of default "
                "filters, unless they are specified as arguments: "
                "no_9p_export,no_virtio_rng,no_pci_assignable,smallpages,"
                "default_bios,bridge,image_backend,multihost. This can be used"
                " to eg. run hugepages tests by filtering 'smallpages' via "
                "this option.")
    add_option(parser,
               dest='vt.filter.default_filters',
               arg='--vt-filter-default-filters',
               nargs='+',
               help=help_msg)


def add_qemu_bin_vt_option(parser):
    """
    Add qemu-bin vt option to parser
    """

    def _str_or_none(arg):
        if arg is None:
            return "Could not find one"
        else:
            return arg

    try:
        qemu_bin_path = standalone_test.find_default_qemu_paths()[0]
    except (RuntimeError, utils_path.CmdNotFoundError):
        qemu_bin_path = None
    qemu_bin = get_settings_value('vt.qemu', 'qemu_bin',
                                  default=None)
    if qemu_bin is None:  # Allow default to be None when not set in setting
        default_qemu_bin = None
        qemu_bin = qemu_bin_path
    else:
        default_qemu_bin = qemu_bin

    help_msg = ("Path to a custom qemu binary to be tested. If --vt-config is "
                "provided and this flag is omitted, no attempt to set the "
                "qemu binaries will be made. Current: %s" %
                _str_or_none(qemu_bin))
    add_option(parser,
               dest='vt.qemu.qemu_bin',
               arg='--vt-qemu-bin',
               default=default_qemu_bin,
               help=help_msg)

    qemu_dst = get_settings_value('vt.qemu', 'qemu_dst_bin',
                                  default=qemu_bin_path)
    help_msg = ("Path to a custom qemu binary to be tested for the destination"
                " of a migration, overrides --vt-qemu-bin. If --vt-config is "
                "provided and this flag is omitted, no attempt to set the qemu"
                " binaries will be made. Current: %s" % _str_or_none(qemu_dst))
    add_option(parser,
               dest='vt.qemu.qemu_dst_bin',
               arg='--vt-qemu-dst-bin',
               default=qemu_dst,
               help=help_msg)


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
        run_subcommand_parser = parser.subcommands.choices.get('run', None)
        if run_subcommand_parser is None:
            return

        vt_compat_group_common = run_subcommand_parser.add_argument_group(
            'Virt-Test compat layer - Common options')
        vt_compat_group_qemu = run_subcommand_parser.add_argument_group(
            'Virt-Test compat layer - QEMU options')
        vt_compat_group_libvirt = run_subcommand_parser.add_argument_group(
            'Virt-Test compat layer - Libvirt options')

        add_basic_vt_options(vt_compat_group_common)
        add_qemu_bin_vt_option(vt_compat_group_qemu)

        help_msg = "List of 'key=value' pairs passed to cartesian parser."
        add_option(parser=vt_compat_group_qemu,
                   dest='vt.extra_params',
                   arg='--vt-extra-params',
                   action='append',
                   help=help_msg)

        supported_uris = ", ".join(SUPPORTED_LIBVIRT_URIS)
        help_msg = ("Choose test connect uri for libvirt (E.g: %s). Current: "
                    "%%(default)s" % supported_uris)
        uri_current = get_settings_value('vt.libvirt', 'connect_uri',
                                         default=None)
        add_option(parser=vt_compat_group_libvirt,
                   dest='vt.libvirt.connect_uri',
                   arg='--vt-connect-uri',
                   default=uri_current,
                   help=help_msg)

    def run(self, config):
        """
        Run test modules or simple tests.
        :param config: Command line args received from the run subparser.
        """
        loader.register_plugin(VirtTestLoader)
