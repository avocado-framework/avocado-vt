import logging
import resource

from virttest.test_setup.core import Setuper

LOG = logging.getLogger("avocado." + __name__)


class UlimitConfig(Setuper):
    """
    Enable to config ulimit.

    Supported options:

    vt_ulimit_core: The maximum size (in bytes) of a core file
                    that the current process can create.
    vt_ulimit_nofile: The maximum number of open file descriptors
                      for the current process.
    vt_ulimit_memlock: The maximum size a process may lock into memory.
    """

    ulimit_options = {
        "core": resource.RLIMIT_CORE,
        "nofile": resource.RLIMIT_NOFILE,
        "memlock": resource.RLIMIT_MEMLOCK,
    }

    def _set(self):
        self.ulimit = {}
        for key in self.ulimit_options:
            set_value = self.params.get("vt_ulimit_%s" % key)
            if not set_value:
                continue
            # get default ulimit values in tuple (soft, hard)
            self.ulimit[key] = resource.getrlimit(self.ulimit_options[key])

            LOG.info("Setting ulimit %s to %s." % (key, set_value))
            if set_value == "ulimited":
                set_value = resource.RLIM_INFINITY
            elif set_value.isdigit():
                set_value = int(set_value)
            else:
                self.test.error(
                    "%s is not supported for " "setting ulimit %s" % (set_value, key)
                )
            try:
                resource.setrlimit(self.ulimit_options[key], (set_value, set_value))
            except ValueError as error:
                self.test.error(str(error))

    def _restore(self):
        for key in self.ulimit:
            LOG.info("Setting ulimit %s back to its default." % key)
            resource.setrlimit(self.ulimit_options[key], self.ulimit[key])

    def setup(self):
        self._set()

    def cleanup(self):
        self._restore()
