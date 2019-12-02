"""
QEMU related utility functions.
"""
import re

from avocado.utils import process


QEMU_VERSION_RE = re.compile(r"QEMU (?:PC )?emulator version\s"
                             r"([0-9]+\.[0-9]+\.[0-9]+)"
                             r"(?:\s\((.*?)\))?")


def get_qemu_version(bin_path):
    """
    Return normalized qemu version and package version

    :param bin_path: Path to qemu binary
    :raise OSError: If unable to get that
    :return: A tuple of normalized version and package version
    """
    output = process.system_output("%s -version" % bin_path,
                                   verbose=False,
                                   ignore_status=True).decode()
    matches = QEMU_VERSION_RE.match(output)
    if matches is None:
        raise OSError('Unable to get the version of qemu')
    return matches.groups()
