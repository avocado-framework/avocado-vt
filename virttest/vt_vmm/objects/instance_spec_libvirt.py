from ..objects import instance_spec


class LibvirtSpec(instance_spec.Spec):
    def __init__(self, name, vt_params, node):
        super(LibvirtSpec, self).__init__(name, "libvirt", vt_params, node)

    def _parse_params(self):
        raise NotImplementedError
