"""
QEMU related utility functions.
"""
import re
import json

from avocado.utils import process

QEMU_VERSION_RE = re.compile(r"QEMU (?:PC )?emulator version\s"
                             r"([0-9]+\.[0-9]+\.[0-9]+)"
                             r"(?:\s\((.*?)\))?")
DEVICE_CATEGORY_RE = re.compile(r"([A-Z]\S+) devices:")


def _get_info(bin_path, options, include_stderr=False):
    """
    Execute a qemu command and return its stdout

    :param bin_path: Path to qemu binary
    :param options: Command line to run
    :param include_stderr: Whether to also include stderr content (besides
                           stdout)
    :return: Command stdout
    """
    qemu_cmd = "%s %s" % (bin_path, options)
    result = process.run(qemu_cmd, verbose=False, ignore_status=True)
    output = result.stdout_text.strip()
    if include_stderr:
        output += result.stderr_text.strip()
    return output


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
    output = _get_info(bin_path, r"-machine help", True)
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
    :return: A dict of all devices
    """
    qemu_devices = {}
    output = _get_info(bin_path, "-device help", True)
    require_machine = "No machine specified" in output
    # Some architectures (arm) require machine type to be always set, but this
    # function is not yet supported
    if require_machine:
        return qemu_devices

    for device_info in output.split("\n\n"):
        device_type = DEVICE_CATEGORY_RE.match(device_info)
        if device_type:
            device_type = device_type.group(1)
            devs_info = re.findall(r'^name "(\S+)"(.*)', device_info,
                                   re.M)
            qemu_devices[device_type] = {dev[0]: dev[1].replace(", ", "", 1)
                                         for dev in devs_info}
    if category:
        return qemu_devices.get(category, {})
    return {k: v for d in qemu_devices.values() for k, v in d.items()}


def get_supported_devices_list(bin_path, category=None):
    """
    Return all devices supported by qemu

    :param bin_path: Path to qemu binary
    :param category: device category (e.g. 'USB', 'Network', 'CPU')
    :return: A list of all devices supported by qemu
    """
    return list(get_devices_info(bin_path, category).keys())


def has_device_category(bin_path, category):
    """
    Check if device category is included in the qemu devices info

    :param bin_path: Path to qemu binary
    :param category: device category (e.g. 'USB', 'Network', 'CPU')
    :return: True if device category existed in qemu devices help info
    """
    out = _get_info(bin_path, "-device help", True)
    return category in DEVICE_CATEGORY_RE.findall(out)


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
    # TODO: Extract the process of executing QMP as a separate method
    output = process.run('echo -e \''
                         '{ "execute": "qmp_capabilities" }\n'
                         '{ "execute": "query-machines", "id": "TEMP-INST" }\n'
                         '{ "execute": "quit" }\''
                         '| %s -M none -nodefaults -nographic -S -qmp stdio '
                         '| grep return | grep TEMP-INST' % bin_path,
                         ignore_status=True, shell=True,
                         verbose=False).stdout_text
    machines = json.loads(output)["return"]
    try:
        machines_info = {machine.pop("name"): machine for machine in machines}
        return machines_info[machine_type]["cpu-max"]
    except KeyError:
        raise ValueError("Could not get the maximum limit CPUs supported by "
                         "this machine '%s'" % machine_type)


def get_dev_attrs(bin_path, opt_name, dev_name, machine="none"):
    """
    Get the device attributes from qemu help doc

    :param bin_path: Path to qemu binary
    :param opt_name: qemu option name
    :param dev_name: qemu device name
    :param machine: machine type
    :return: attributes list
    """
    help_doc = process.run("%s -M %s -%s %s,?" % (bin_path, machine, opt_name,
                           dev_name), verbose=False, ignore_status=True,
                           shell=True).stdout_text
    attrs = re.findall(r'\s*([\w|-]+)=', help_doc, re.M)
    return attrs
