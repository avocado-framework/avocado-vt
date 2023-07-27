import logging

from virttest.qemu_devices import qdevices, qcontainer

from . import InstanceDriver

LOG = logging.getLogger("avocado.agent." + __name__)


class QemuInstanceDriver(InstanceDriver):
    def __init__(self, spec):
        super(QemuInstanceDriver, self).__init__("qemu", spec)

    def create_devices(self):

        def _add_name(name):
            return " -name '%s'" % name

        def _process_sandbox(devices, action):
            if action == "add":
                if devices.has_option("sandbox"):
                    return " -sandbox on "
            elif action == "rem":
                if devices.has_option("sandbox"):
                    return " -sandbox off "

        qemu_binary = "/usr/libexec/qemu-kvm"
        name = self._params.get("name")
        self._devices = qcontainer.DevContainer(qemu_binary, name)
        StrDev = qdevices.QStringDevice

        self._devices.insert(StrDev('qemu', cmdline=qemu_binary))

        qemu_preconfig = self._params.get("qemu_preconfig")
        if qemu_preconfig:
            self._devices.insert(StrDev('preconfig', cmdline="--preconfig"))

        self._devices.insert(StrDev('vmname', cmdline=_add_name(name)))

        qemu_sandbox = self._params.get("qemu_sandbox")
        if qemu_sandbox == "on":
            self._devices.insert(
                StrDev('qemu_sandbox', cmdline=_process_sandbox(self._devices, "add")))
        elif qemu_sandbox == "off":
            self.devices.insert(
                StrDev('qemu_sandbox', cmdline=_process_sandbox(self._devices, "rem")))

        defaults = self._params.get("defaults", "no")
        if self._devices.has_option("nodefaults") and defaults != "yes":
            self._devices.insert(StrDev('nodefaults', cmdline=" -nodefaults"))

        return self._devices

    def make_cmdline(self):
        self._cmd = self._devices.cmdline()
        return self._cmd
