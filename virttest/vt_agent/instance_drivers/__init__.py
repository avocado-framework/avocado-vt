import json
import signal
from functools import partial

import six

from abc import ABCMeta
from abc import abstractmethod

import aexpect

from . import qemu
from . import libvirt


@six.add_metaclass(ABCMeta)
class InstanceDriver(object):
    def __init__(self, kind, spec):
        self._kind = kind
        self._params = json.loads(spec)
        self._process = None
        self._cmd = None
        self._devices = None

    @abstractmethod
    def create_devices(self):
        raise NotImplementedError

    @abstractmethod
    def make_cmdline(self):
        raise NotImplementedError
    
    def run_cmdline(self, command, termination_func=None, output_func=None,
                    output_prefix="", timeout=1.0, auto_close=True, pass_fds=(),
                    encoding=None):
        self._process = aexpect.run_tail(
            command, termination_func, output_func, output_prefix,
            timeout, auto_close, pass_fds, encoding)

    def get_pid(self):
        return self._process.get_pid()

    def get_status(self):
        return self._process.get_status()

    def get_output(self):
        return self._process.get_output()

    def is_alive(self):
        return self._process.is_alive()

    def kill(self, sig=signal.SIGKILL):
        self._process.kill(sig)


def get_instance_driver(kind, spec):
    instance_drivers = {
        "qemu": qemu.QemuInstanceDriver(spec),
        "libvirt": libvirt.LibvirtInstanceDriver(spec),
    }

    if kind not in instance_drivers:
        raise OSError("No support the %s instance driver" % kind)
    return instance_drivers.get(kind, spec)
