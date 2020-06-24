"""
This module provides interfaces about NVMe storage backend.

Available functions:
- get_image_filename: Get the image filename from NVMe.
- file_exists: Check whether the NVMe image file exists.
- parse_uri: Parse the URI from NVMe image filename.

"""
import re

from avocado.utils import process

from virttest import utils_misc


def get_image_filename(address, namespace):
    """
    Get the image filename from NVMe.

    :param address: The PCI address NVMe,
                    format: $domain:$bus:$slot.$function/$namespace.
    :type address: str
    :param namespace: The namespace number starting according to the NVMe spec.
    :type namespace: str
    :return: The image filename from NVMe,
             the format of nmve://$domain:$bus:$slot.$function/$namespace
             e.g: nvme://0000:44:00.0/1
    :rtype: str
    """
    return 'nvme://%s/%s' % (address, namespace)


def file_exists(params, filename):
    """
    Check whether the NVMe image file exists.

    :param params: A dict containing image parameters.
    :type params: dict
    :param filename: The NVMe image filename.
    :type filename: str
    :return: True if the NVMe image file exists, else False
    :rtype: bool
    """
    cmd = "%s info %s" % (utils_misc.get_qemu_img_binary(params), filename)
    o = process.run(cmd, 60, False, True).stdout_text.strip()
    return params.get('image_format') in o


def parse_uri(filename):
    """
    Get the address and namespace from NVMe image filename.

    :param filename: The NVMe filename,
                     format of nmve://$domain:$bus:$slot.$function/$namespace
    :return: The tuples: (address, namespace)
    :rtype: tuple
    """
    return re.match(r'nvme://(\w+:\w+:\w+\.\w+)/(\w+)', filename).groups()
