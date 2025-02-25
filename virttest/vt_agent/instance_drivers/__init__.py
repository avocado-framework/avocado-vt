import json
import signal
import time
import glob
import os

from virttest import utils_misc
from virttest import data_dir

from abc import ABCMeta, abstractmethod
from functools import partial

import aexpect
import six


from managers import connect_mgr


@six.add_metaclass(ABCMeta)
class InstanceDriver(object):
    def __init__(self, instance_id, kind):
        self._instance_id = instance_id
        self._kind = kind
        self._devices = None
        self._cmdline = None
        self.monitors = []
        self._serials = {}
        self._driver_id = self._generate_unique_id()

    def get_devices(self):
        return self._devices

    def get_cmdline(self):
        return self._cmdline

    def get_serials(self):
        return self._serials

    @property
    def monitor(self):
        self.monitors = connect_mgr.get_connects_by_instance(self._instance_id)
        return self.monitors[0] if self.monitors else None

    @staticmethod
    def _generate_unique_id():
        """
        Generate a unique identifier for this driver
        """
        while True:
            driver_id = time.strftime(
                "%Y%m%d-%H%M%S-"
            ) + utils_misc.generate_random_string(8)
            if not glob.glob(
                    os.path.join(data_dir.get_tmp_dir(), "*%s" % driver_id)
            ):
                return driver_id

    @abstractmethod
    def create_devices(self, spec):
        raise NotImplementedError

    @abstractmethod
    def make_cmdline(self, migrate_inc_uri=None):
        raise NotImplementedError

    def start(self, cmdline):
        raise NotImplementedError

    def stop(self, graceful=True, timeout=60, shutdown_cmd=None):
        raise NotImplementedError

    def cleanup(self, free_mac_addresses=True):
        raise NotImplementedError

    def create_console_connections(self):
        raise NotImplementedError

    def get_proc_pid(self):
        raise NotImplementedError

    def get_proc_status(self):
        raise NotImplementedError

    def get_proc_output(self):
        raise NotImplementedError

    def is_proc_alive(self):
        raise NotImplementedError

    def is_proc_defunct(self):
        raise NotImplementedError

    def get_pid(self):
        raise NotImplementedError

    def kill_proc(self, sig=signal.SIGKILL):
        raise NotImplementedError

    def get_serial_consoles(self):
        raise NotImplementedError

    def get_vnc_consoles(self):
        raise NotImplementedError

    def get_spice_consoles(self):
        raise NotImplementedError
