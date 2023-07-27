from . import InstanceDriver


class LibvirtInstanceDriver(InstanceDriver):
    def __init__(self):
        super(LibvirtInstanceDriver, self).__init__("libvirt")

    def create_devices(self, spec):
        pass

    def make_cmdline(self):
        pass
