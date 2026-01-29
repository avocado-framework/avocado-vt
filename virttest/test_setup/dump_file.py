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

from avocado.utils import linux_modules

from virttest import utils_package
from virttest.test_setup.core import Setuper

LOG = logging.getLogger(__name__)


class DumpFileSetup(Setuper):
    _nbd_is_loaded_by_vt = False

    def setup(self):
        # TODO: add the required packages by libvirt or qemu.
        _pkg = []
        try:
            if _pkg:
                utils_package.package_install(_pkg)

            linux_modules.load_module("nbd")
            self._nbd_is_loaded_by_vt = True
            LOG.debug("The dump_file is set up successfully.")
        except Exception as e:
            LOG.error("The dump_file failed to set up.", exc_info=e)

    def cleanup(self):
        if self._nbd_is_loaded_by_vt:
            linux_modules.unload_module("nbd")
            LOG.debug("The dump_file is cleanup successfully.")
        else:
            LOG.debug("Skip the dump_file cleanup.")
