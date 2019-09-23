import logging

from avocado.core import exceptions
from avocado.utils import process


def create_volume(volume):
    if volume.preallocation == "full":
        if volume.pool.available < volume.capacity:
            raise exceptions.TestError(
                "No enough free space, request '%s' but available in %s is '%s'" % (
                    volume.capacity, volume.pool.name, volume.pool.available))
    else:
        if volume.format == "qcow2":
            if volume.pool.available * 1.2 < volume.capacity:
                raise exceptions.TestError(
                    "No enough free space, request '%s' but available in %s is '%s'" % (
                        volume.capacity, volume.pool.name, volume.pool.available))
    options = volume.generate_qemu_img_options()
    cmd = "qemu-img create %s %s %sB" % (options, volume.key, volume.capacity)
    logging.debug("create volume cmd: %s" % cmd)
    process.system(cmd, shell=True, ignore_status=False)
