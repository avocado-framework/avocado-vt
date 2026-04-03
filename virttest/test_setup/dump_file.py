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
# Copyright: Red Hat Inc. 2026
# Authors: Houqi (Nick) Zuo <hzuo@redhat.com>

import logging

from avocado.utils import linux_modules, process

from virttest import utils_package
from virttest.test_setup.core import Setuper

LOG = logging.getLogger(__name__)


class DumpFileSetup(Setuper):
    _nbd_is_loaded_by_vt = False

    def setup(self):
        if self.params.get("vm_memory_dump_method") in ("nbd",):
            # TODO:
            #  1. add the required packages by libvirt or qemu.
            #  2. classify the required packages by online/offline.
            _pkg = []
            try:
                if _pkg:
                    utils_package.package_install(_pkg)

                process.system("dnf install -y nbd", ignore_status=True)
                if not linux_modules.module_is_loaded(
                    "nbd"
                ) and linux_modules.load_module("nbd"):
                    self._nbd_is_loaded_by_vt = True
                    LOG.debug("The dump_file setuper is set up successfully.")
                else:
                    LOG.debug("Module nbd was loaded.")
            except Exception as e:
                LOG.debug("The dump_file setuper failed to set up.", exc_info=e)
        else:
            LOG.debug("Nothing to do. Skip the dump_file setuper setup.")

    def cleanup(self):
        if self._nbd_is_loaded_by_vt:
            if linux_modules.unload_module("nbd"):
                LOG.debug("The dump_file setuper is cleanup successfully.")
        else:
            LOG.debug("Nothing to do. Skip the dump_file setuper cleanup.")
