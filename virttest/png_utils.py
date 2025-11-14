"""
Utility functions to deal with PNG (virsh screendump format) files.
"""

import logging
import struct

from virttest import libvirt_version, utils_misc

LOG = logging.getLogger("avocado." + __name__)


def should_use_png_format(vm, params):
    """
    Determine whether to use PNG format based on QEMU and libvirt versions

    :param vm: VM object
    :param params: Test params
    :return: Returns True to use PNG format, or False to use PPM
    """
    try:
        qemu_supports_png = utils_misc.compare_qemu_version(7, 1, 0, False, params)
        libvirt_supports_png = libvirt_version.version_compare(9, 0, 0)
        return qemu_supports_png and libvirt_supports_png
    except Exception as e:
        LOG.warning("Version detection failed: %s, falling back to PPM", e)
        return False


def image_verify_png_file(filename):
    """
    Verify the validity of a PNG file.

    :param filename: Path of the file being verified.
    :return: True if filename is a valid PNG image file. This function
             reads only the first few bytes of the file so it should be rather
             fast.
    """
    try:
        with open(filename, "rb") as fin:
            # PNG signature: 8 bytes
            png_signature = b"\x89PNG\r\n\x1a\n"
            signature = fin.read(8)
            assert signature == png_signature

            # Read IHDR chunk (Image Header)
            # Next 4 bytes: chunk length (should be 13 for IHDR)
            chunk_length = struct.unpack(">I", fin.read(4))[0]
            assert chunk_length == 13

            # Next 4 bytes: chunk type (should be 'IHDR')
            chunk_type = fin.read(4)
            assert chunk_type == b"IHDR"

            # IHDR data: width (4), height (4), bit depth (1), color type (1),
            # compression (1), filter (1), interlace (1)
            width = struct.unpack(">I", fin.read(4))[0]
            height = struct.unpack(">I", fin.read(4))[0]
            assert width > 0 and height > 0

            bit_depth = struct.unpack("B", fin.read(1))[0]
            color_type = struct.unpack("B", fin.read(1))[0]
            compression = struct.unpack("B", fin.read(1))[0]
            filter_method = struct.unpack("B", fin.read(1))[0]
            interlace = struct.unpack("B", fin.read(1))[0]

            # Validate PNG header values
            assert bit_depth in [1, 2, 4, 8, 16]
            assert color_type in [0, 2, 3, 4, 6]
            assert compression == 0  # Only compression method 0 is defined
            assert filter_method == 0  # Only filter method 0 is defined
            assert interlace in [0, 1]  # 0 = no interlace, 1 = Adam7 interlace

        return True
    except Exception:
        return False
