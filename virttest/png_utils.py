"""
Utility functions to deal with PNG (virsh screendump format) files.
"""

import logging
import struct

LOG = logging.getLogger("avocado." + __name__)


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
            if signature != png_signature:
                return False

            # Read IHDR chunk (Image Header)
            # Next 4 bytes: chunk length (should be 13 for IHDR)
            length_bytes = fin.read(4)
            if len(length_bytes) != 4:
                return False
            chunk_length = struct.unpack(">I", length_bytes)[0]
            if chunk_length != 13:
                return False

            # Next 4 bytes: chunk type (should be 'IHDR')
            chunk_type = fin.read(4)
            if chunk_type != b"IHDR":
                return False
            width_bytes = fin.read(4)
            height_bytes = fin.read(4)
            if len(width_bytes) != 4 or len(height_bytes) != 4:
                return False
            width = struct.unpack(">I", width_bytes)[0]
            height = struct.unpack(">I", height_bytes)[0]
            if width <= 0 or height <= 0:
                return False
            fields = fin.read(5)
            if len(fields) != 5:
                return False
            bit_depth, color_type, compression, filter_method, interlace = (
                struct.unpack("BBBBB", fields)
            )

            # Validate PNG header values
            if bit_depth not in (1, 2, 4, 8, 16):
                return False
            if color_type not in (0, 2, 3, 4, 6):
                return False
            if compression != 0 or filter_method != 0:
                return False
            if interlace not in (0, 1):
                return False
    except (OSError, struct.error) as exc:
        LOG.debug("PNG verification failed for %s: %s", filename, exc)
        return False
    return True
