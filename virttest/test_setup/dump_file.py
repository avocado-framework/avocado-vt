import logging

from avocado.utils import linux_modules

from virttest import utils_package
from virttest.test_setup.core import Setuper

LOG = logging.getLogger(__name__)


class DumpFileSetup(Setuper):
    _nbd_is_loaded_by_vt = False

    def setup(self):
        # "qemu-nbd" is required by qemu in vm_type.
        # "ntfs-3g" is required by ntfs filesystem.
        # TODO: add the required packages by libvirt.
        _pkg = ["ntfs-3g"]
        try:
            utils_package.package_install(_pkg)

            if not linux_modules.module_is_loaded("nbd"):
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
