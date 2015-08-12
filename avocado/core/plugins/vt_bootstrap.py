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

import sys

from avocado.core.plugins import plugin

from virttest import bootstrap
from virttest import defaults

from virttest.standalone_test import SUPPORTED_TEST_TYPES


class VirtBootstrap(plugin.Plugin):

    """
    Implements the avocado 'vt-bootstrap' subcommand
    """

    name = 'virt_test_compat_bootstrap'
    enabled = True

    def configure(self, parser):
        self.parser = parser.subcommands.add_parser('vt-bootstrap',
                                                    help=('Setup tests for the '
                                                          'virt test '
                                                          'compatibility '
                                                          'layer'))
        self.parser.add_argument("--vt-type", action="store",
                                 help=("Choose test type (%s)" %
                                       ", ".join(SUPPORTED_TEST_TYPES)),
                                 default='qemu')
        self.parser.add_argument("--vt-guest-os", action="store",
                                 default=None,
                                 help=("Select the guest OS to be used. "
                                       "If -c is provided, this will be "
                                       "ignored. Default: %s" %
                                       defaults.DEFAULT_GUEST_OS))
        self.parser.add_argument("--vt-selinux-setup", action="store_true",
                                 default=False,
                                 help="Define default contexts of directory.")
        self.parser.add_argument("--vt-no-downloads", action="store_true",
                                 default=False,
                                 help="Do not attempt to download JeOS images")
        self.parser.add_argument("--vt-update-config", action="store_true",
                                 default=False, help=("Forces configuration "
                                                      "updates (all manual "
                                                      "config file editing "
                                                      "will be lost). "
                                                      "Requires --vt-type "
                                                      "to be set"))
        self.parser.add_argument("--vt-update-providers", action="store_true",
                                 default=False, help=("Forces test "
                                                      "providers to be "
                                                      "updated (git repos "
                                                      "will be pulled)"))
        self.parser.add_argument("--yes-to-all", action="store_true",
                                 default=False, help=("All interactive "
                                                      "questions will be "
                                                      "answered with yes (y)"))
        super(VirtBootstrap, self).configure(self.parser)

    def run(self, args):
        args.vt_config = None
        args.vt_verbose = True
        args.vt_log_level = 'debug'
        args.vt_console_level = 'debug'
        args.vt_arch = None
        args.vt_machine_type = None
        args.vt_keep_image = False
        args.vt_keep_guest_running = False
        args.vt_keep_image_between_tests = False
        args.vt_mem = 1024
        args.vt_no_filter = ''
        args.vt_qemu_bin = None
        args.vt_dst_qemu_bin = None
        args.vt_nettype = 'user'
        args.vt_only_type_specific = False
        args.vt_tests = ''
        args.vt_connect_uri = 'qemu:///system'
        args.vt_accel = 'kvm'
        args.vt_monitor = 'human'
        args.vt_smp = 1
        args.vt_image_type = 'qcow2'
        args.vt_nic_model = 'virtio_net'
        args.vt_disk_bus = 'virtio_blk'
        args.vt_vhost = 'off'
        args.vt_malloc_perturb = 'yes'
        args.vt_qemu_sandbox = 'on'
        args.vt_tests = ''
        args.show_job_log = False
        args.test_lister = True

        bootstrap.bootstrap(options=args, interactive=True)
        sys.exit(0)
