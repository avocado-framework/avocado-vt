"""
Utility functions to deal with PNG (virsh screendump format) files.
"""

import logging
import struct

from .ppm_utils import add_timestamp

LOG = logging.getLogger("avocado." + __name__)


def add_png_timestamp(image, timestamp, margin=2):
    """
    Add timestamp for png format file.
    """
    return add_timestamp(image, timestamp, margin=margin)


def image_verify_png_file(filename):
    """
    Verify the validity of a PNG file by inspecting its signature and IHDR chunk.

    This function performs a "shallow" validation by reading only the first
    33 bytes of the file, making it extremely fast for pre-screening uploads.

    :param filename: Path to the file.
    :return: True if the file has a valid PNG signature and header, False otherwise.
    """
    # Standard PNG 8-byte signature
    PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

    try:
        with open(filename, "rb") as f:
            # 1. Verify Magic Number Signature
            if f.read(8) != PNG_SIGNATURE:
                return False

            # 2. Read IHDR (Image Header) Chunk
            # Structure: Length(4), Type(4), Width(4), Height(4),
            # BitDepth(1), ColorType(1), Compression(1), Filter(1), Interlace(1)
            # Total bytes to read = 4 + 4 + 4 + 4 + 1 + 1 + 1 + 1 + 1 = 21 bytes
            ihdr_data = f.read(21)
            if len(ihdr_data) < 21:
                return False

            # Unpack binary data:
            # >: Big-endian (Network byte order)
            # I: unsigned int (4 bytes), 4s: char[4] (4 bytes), 5B: 5 unsigned chars (5 bytes)
            fmt = ">I4sII5B"
            length, chunk_type, width, height, bd, ct, comp, filt, interl = (
                struct.unpack(fmt, ihdr_data)
            )

            # 3. Validation Logic
            # IHDR must have length 13 and correct type
            if chunk_type != b"IHDR" or length != 13:
                return False

            # Dimensions must be positive
            if width <= 0 or height <= 0:
                return False

            # Validate Bit Depth and Color Type combinations
            if bd not in (1, 2, 4, 8, 16) or ct not in (0, 2, 3, 4, 6):
                return False

            # Per PNG Spec: Compression and Filter must be 0
            if comp != 0 or filt != 0:
                return False

            # Interlace method: 0 (None) or 1 (Adam7)
            if interl not in (0, 1):
                return False

    except (OSError, struct.error) as exc:
        LOG.debug("PNG verification failed for %s: %s", filename, exc)
        return False

    return True
