import json

import six

from abc import ABCMeta
from abc import abstractmethod

from . import qemu
from . import libvirt


@six.add_metaclass(ABCMeta)
class SpecHelper(object):
    def __init__(self, kind=None):
        self._kind = kind
        self._spec = None

    @abstractmethod
    def _parse_params(self, params):
        raise NotImplementedError

    def to_json(self, params):
        self._spec = self._parse_params(params)
        return json.dumps(self._spec)


def get_spec_helper(kind):
    spec_helpers = {
        "qemu": qemu.QemuSpecHelper(),
        "libvirt": libvirt.LibvirtSpecHelper(),
    }

    if kind not in spec_helpers:
        raise OSError("No support the %s spec" % kind)
    return spec_helpers.get(kind)
