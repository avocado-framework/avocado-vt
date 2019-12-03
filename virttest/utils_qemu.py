"""
QEMU related utility functions.
"""
import re

from avocado.utils import process

QEMU_VERSION_RE = re.compile(r"QEMU (?:PC )?emulator version\s"
                             r"([0-9]+\.[0-9]+\.[0-9]+)"
                             r"(?:\s\((.*?)\))?")


def _get_info(bin_path, options, allow_output_check=None):
    """
    Execute a qemu command and return its stdout

    :param bin_path: Path to qemu binary
    :param options: Command line to run
    :param allow_output_check: Record the output from stdout/stderr
    :return: Command stdout
    """
    qemu_cmd = "%s %s" % (bin_path, options)
    return process.run(qemu_cmd, verbose=False, ignore_status=True,
                       allow_output_check=allow_output_check).stdout_text.strip()


def get_qemu_version(bin_path):
    """
    Return normalized qemu version and package version

    :param bin_path: Path to qemu binary
    :raise OSError: If unable to get that
    :return: A tuple of normalized version and package version
    """
    output = _get_info(bin_path, "-version")
    matches = QEMU_VERSION_RE.match(output)
    if matches is None:
        raise OSError('Unable to get the version of qemu')
    return matches.groups()


def get_machines_info(bin_path):
    """
    Return all machines information supported by qemu

    :param bin_path: Path to qemu binary
    :return: A dict of all machines
    """
    output = _get_info(bin_path, r"-machine help", allow_output_check="combined")
    machines = re.findall(r"^([a-z]\S+)\s+(.*)$", output, re.M)
    return dict(machines)


def get_supported_machines_list(bin_path):
    """
    Return all machines supported by qemu

    :param bin_path: Path to qemu binary
    :return: A list of all machines supported by qemu
    """
    return list(get_machines_info(bin_path).keys())


def get_devices_info(bin_path, category=None):
    """
    Return all devices information supported by qemu

    :param bin_path: Path to qemu binary
    :param category: device category (e.g. 'USB', 'Network', 'CPU')
    :return:  A dict of all devices
    """
    output = _get_info(bin_path, r"-device help", allow_output_check="combined")
    qemu_devices = {}
    for device_info in output.split("\n\n"):
        device_type = re.match(r"([A-Z]\S+) devices:", device_info).group(1)
        devs_info = re.findall(r'^name "(\S+)"(.*)', device_info, re.M)
        qemu_devices[device_type] = {dev[0]: dev[1].replace(", ", "", 1)
                                     for dev in devs_info}
    if category:
        return qemu_devices[category]
    return {k: v for d in qemu_devices.values() for k, v in d.items()}


def get_supported_devices_list(bin_path, category=None):
    """
    Return all devices supported by qemu

    :param bin_path: Path to qemu binary
    :param category: device category (e.g. 'USB', 'Network', 'CPU')
    :return: A list of all devices supported by qemu
    """
    return list(get_devices_info(bin_path, category).keys())


def find_supported_devices(bin_path, pattern, category=None):
    """
    Use pattern to find all matching devices.

    :param bin_path: Path to qemu binary
    :param pattern: pattern to search the most suitable device
    :param category: device category (e.g. 'USB', 'Network', 'CPU')
    :return: device list
    """
    devices = []
    for device in get_supported_devices_list(bin_path, category):
        if re.match(pattern, device):
            devices.append(device)
    return devices


def get_maxcpus_hard_limit(bin_path, machine_type):
    """
    Return maximum limit CPUs supported by specified machine type

    :param bin_path: Path to qemu binary
    :param machine_type: One machine type supported by qemu
    :raise ValueError: If unable to get that
    :return: Maximum value of vCPU
    """
    invalid_maximum = 0x7fffffff
    output = _get_info(bin_path, r"-machine %s -smp maxcpus=%d"
                       % (machine_type, invalid_maximum),
                       allow_output_check="combined")
    searches = re.search(r"'%s.*' is (\d+)" % machine_type, output)
    if searches is None:
        raise ValueError("Could not get the maximum limit CPUs supported by "
                         "this machine '%s'" % machine_type)
    return int(searches.group(1))
