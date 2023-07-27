from . import InstanceDriver


class LibvirtInstanceDriver(InstanceDriver):
    def __init__(self, spec):
        super(LibvirtInstanceDriver, self).__init__("libvirt", spec)

    def create_devices(self):
        pass

    def make_cmdline(self):
        pass
