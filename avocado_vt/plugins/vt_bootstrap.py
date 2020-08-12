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
from avocado.core.plugin_interfaces import CLICmd

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
                            default='qemu', dest='vt.type')
        parser.add_argument("--vt-guest-os", action="store",
                            default="%s.%s" % (defaults.DEFAULT_GUEST_OS,
                                               defaults.ARCH),
                            help=("Select the guest OS to be used  "
                                  "optionally followed by guest arch. "
                                  "If -c is provided, this will be "
                                  "ignored. Default: %(default)s"),
                            dest='vt.guest_os')
        parser.add_argument("--vt-selinux-setup", action="store_true",
                            default=False,
                            help="Define default contexts of directory.")
        parser.add_argument("--vt-no-downloads", action="store_true",
                            default=False,
                            help="Do not attempt any download")
        parser.add_argument("--vt-skip-verify-download-assets",
                            action='store_true', default=False,
                            help=("Skip the bootstrap phase that verifies "
                                  "and possibly downloads assets files "
                                  "(usually a JeOS image)"))
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

    def run(self, config):
        # Enable root logger as some Avocado-vt libraries use that
        handler = logging.StreamHandler()
        handler.setLevel(logging.DEBUG)
        logging.getLogger("").addHandler(handler)

        try:
            bootstrap.bootstrap(options=config, interactive=True)
            sys.exit(0)
        except process.CmdError as ce:
            if ce.result.interrupted:
                logging.info('Bootstrap command interrupted by user')
                logging.info('Command: %s', ce.command)
            else:
                logging.error('Bootstrap command failed')
                logging.error('Command: %s', ce.command)
                if ce.result.stderr_text:
                    logging.error('stderr output:')
                    logging.error(ce.result.stderr_text)
                if ce.result.stdout_text:
                    logging.error('stdout output:')
                    logging.error(ce.result.stdout_text)
            sys.exit(1)
        except KeyboardInterrupt:
            logging.info('Bootstrap interrupted by user')
            sys.exit(1)
