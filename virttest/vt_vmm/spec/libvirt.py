from . import SpecHelper


class LibvirtSpecHelper(SpecHelper):
    def __init__(self):
        super(LibvirtSpecHelper, self).__init__("libvirt")

    def _parse_params(self, params):
        raise NotImplementedError
