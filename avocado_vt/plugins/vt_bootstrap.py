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
import logging

from avocado.utils import process

# Avocado's plugin interface module has changed location. Let's keep
# compatibility with old for at, least, a new LTS release
try:
    from avocado.core.plugin_interfaces import CLICmd
except ImportError:
    from avocado.plugins.base import CLICmd

from virttest import bootstrap
from virttest import defaults
from virttest.standalone_test import SUPPORTED_TEST_TYPES


class VTBootstrap(CLICmd):

    """
    Avocado VT - implements the 'vt-bootstrap' subcommand
    """

    name = 'vt-bootstrap'
    description = "Avocado VT - implements the 'vt-bootstrap' subcommand"

    def configure(self, parser):
        parser = super(VTBootstrap, self).configure(parser)
        parser.add_argument("--vt-type", action="store",
                            help=("Choose test type (%s)" %
                                  ", ".join(SUPPORTED_TEST_TYPES)),
                            default='qemu')
        parser.add_argument("--vt-guest-os", action="store",
                            default=None,
                            help=("Select the guest OS to be used. "
                                  "If -c is provided, this will be "
                                  "ignored. Default: %s" %
                                  defaults.DEFAULT_GUEST_OS))
        parser.add_argument("--vt-selinux-setup", action="store_true",
                            default=False,
                            help="Define default contexts of directory.")
        parser.add_argument("--vt-no-downloads", action="store_true",
                            default=False,
                            help="[obsoleted] Do not attempt to check/"
                            "download asset files (JeOS)")
        parser.add_argument("--vt-skip-assets", action="store_true",
                            dest="vt_no_downloads", help="Skip processing"
                            " asset files (download/check JeOS)")
        parser.add_argument("--vt-skip-providers", action="store_true",
                            help="Skip downloading/updating test providers.")
        parser.add_argument("--vt-update-config", action="store_true",
                            default=False, help=("Forces configuration "
                                                 "updates (all manual "
                                                 "config file editing "
                                                 "will be lost). "
                                                 "Requires --vt-type "
                                                 "to be set"))
        parser.add_argument("--vt-update-providers", action="store_true",
                            default=False, help=("Forces test "
                                                 "providers to be "
                                                 "updated (git repos "
                                                 "will be pulled)"))
        parser.add_argument("--yes-to-all", action="store_true",
                            default=False, help=("All interactive "
                                                 "questions will be "
                                                 "answered with yes (y)"))
        parser.add_argument("--vt-host-distro-name", action="store",
                            metavar="HOST_DISTRO_NAME",
                            help=("The name of the distro to be used when "
                                  "generating the host configuration entry"))
        parser.add_argument("--vt-host-distro-version", action="store",
                            metavar="HOST_DISTRO_VERSION",
                            help=("The version of the distro to be used when "
                                  "generating the host configuration entry"))
        parser.add_argument("--vt-host-distro-release", action="store",
                            metavar="HOST_DISTRO_RELEASE",
                            help=("The release of the distro to be used when "
                                  "generating the host configuration entry."))
        parser.add_argument("--vt-host-distro-arch", action="store",
                            metavar="HOST_DISTRO_ARCH",
                            help=("The architecture of the distro to be used when "
                                  "generating the host configuration entry."))

    def run(self, args):
        # Enable root logger as some Avocado-vt libraries use that
        handler = logging.StreamHandler()
        handler.setLevel(logging.DEBUG)
        logging.getLogger("").addHandler(handler)

        try:
            bootstrap.bootstrap(options=args, interactive=True)
            sys.exit(0)
        except process.CmdError, ce:
            if ce.result.interrupted:
                logging.info('Bootstrap command interrupted by user')
                logging.info('Command: %s', ce.command)
            else:
                logging.error('Bootstrap command failed')
                logging.error('Command: %s', ce.command)
                if ce.result.stderr:
                    logging.error('stderr output:')
                    logging.error(ce.result.stderr)
                if ce.result.stdout:
                    logging.error('stdout output:')
                    logging.error(ce.result.stdout)
            sys.exit(1)
        except KeyboardInterrupt:
            logging.info('Bootstrap interrupted by user')
            sys.exit(1)
