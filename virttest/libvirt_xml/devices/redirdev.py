"""
redirdev device support class(es)

http://libvirt.org/formatdomain.html#elementsRedir
"""

import six

from virttest.libvirt_xml.devices import base


@six.add_metaclass(base.StubDeviceMeta)
class Redirdev(base.TypedDeviceBase):
    # TODO: Write this class
    _device_tag = 'redirdev'
    _def_type_name = 'spicevmc'
