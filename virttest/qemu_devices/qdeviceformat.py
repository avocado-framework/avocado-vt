"""
Representation of qemu devices.

These classes implements various features to generate the
device representations.

:copyright: 2023 Red Hat Inc.
"""
import json
import logging
import re
from abc import ABC

from virttest import utils_numeric
from virttest.qemu_devices.qdevices import QStringDevice

LOG = logging.getLogger('avocado.' + __name__)


def string_to_integer(value, scale):
    """
    Return the value in integer from value in string.

    :params value: the value to be converted
    :type value: string
    :params scale: the expected scale
    :type scale: int
    :return: the integer value
    :rtype: int
    """
    return int(value, scale)


def string_to_decimal(value):
    """
    Return the decimal from value in string.

    :params value: the value to be converted
    :type value: string
    :return: the integer value
    :rtype: int
    """
    return string_to_integer(value, 10)


def string_to_hexadecimal(value):
    """
    Return the hexadecimal from value in string.

    :params value: the value to be converted
    :type value: string
    :return: the integer value
    :rtype: int
    """
    return string_to_integer(value, 16)


def string_to_boolean(value):
    """
    Return boolean based on the value in string.

    :params value: the value to be converted
    :type value: string
    :return: True or False
    :rtype: boolean
    """
    return value in ("yes", "on")


def string_to_b_unit(value):
    """
    Return value in B unit based on the value in string, such as string to
    uint64( "size": "14336M"  to "size": 15032385536 (bytes) )

    :params value: the value to be converted
    :type value: string
    :return: the converted value
    :rtype: int
    """
    return int(utils_numeric.normalize_data_size(value, "B"))


def string_to_int_list(value):
    """
    Return list based on the value in string.

    :params value: the value to be converted
    :type value: string
    :return: the converted value
    :rtype: list[int, int, ...]
    """
    return list(map(int, value.split()))


def int_to_string(value):
    """
    Return string value based on the int value.

    :params value: the value to be converted
    :type value: int
    :return: the converted value
    :rtype: string
    """
    return str(value)


def spec_type_to_string(value):
    """
    Return value based on the value in string.

    :params value: the value to be converted
    :type value: string
    :return: the converted value
    :rtype: string
    """
    if value in (None, ""):
        return ""
    elif value in ("NO_EQUAL_STRING"):
        return "on"
    return value


def _update_json_format_type_mapping(origin, diff):
    """
    Update the origin value based on the diff value and version value.

    :params origin: the data of origin
    :type origin: dict
    :params origin: the data of diff
    :type diff: dict
    """
    for dev_type in diff.keys():
        if dev_type in origin.keys() and isinstance(origin[dev_type], dict):
            _update_json_format_type_mapping(origin[dev_type], diff[dev_type])
        else:
            origin.update(diff)


def flat_to_nested(flat):
    """
    Convert the flat key to the nested key. (e.g: {'cache.direct': 'true'}
    to {'cache': {'direct': 'true'}})

    :params flat: the key in dict structure including the flat key
    :type flat: dict
    :return: the converted key
    :rtype: dict
    """
    res = dict()
    for key, value in flat.items():
        parts = key.split(".", 1)
        if len(parts) > 1:
            res[parts[0]] = flat_to_nested({parts[-1]: value})
        else:
            res[parts[0]] = value

    return res


class QBaseFormat(object):
    """
    Base class of format
    """
    def __init__(self):
        pass

    def qemu_cmdline(self, device):
        raise NotImplementedError

    def hotplug_qmp(self, device):
        raise NotImplementedError

    def unhotplug_qmp(self, device):
        raise NotImplementedError

    def hotplug_hmp(self, device):
        raise NotImplementedError

    def unhotplug_hmp(self, device_id):
        raise NotImplementedError


class JsonFormat(QBaseFormat, ABC):
    """
    Provider some functions for the json format representation of a device.
    """
    def qemu_cmdline(self, device):
        """
        Return qemu command line in the json format representation based on the
        device given.

        :params device: the device object
        :type device: the instance of a QBaseDevice or a QBaseDevice's subclass
        :return: the device representation in json format
        :rtype: string
        """
        params_cp = device.params.copy()
        dev_name = device.params.get("driver", "")
        if device.type is "object":
            params_cp["qom-type"] = params_cp.pop("backend")
            dev_name = params_cp.get("qom-type")
        for key, val in params_cp.items():
            try:
                get_func = json_format_type_mapping.get(device.type).get(
                    dev_name).get(key)
            except AttributeError:
                get_func = None
            finally:
                params_cp[key] = get_func(val) if get_func else val
        # convert the flat params to nested params
        params_cp = flat_to_nested(params_cp)

        out = "-%s " % device.type
        return out + '\'' + json.dumps(params_cp) + '\''

    def hotplug_qmp(self, device):
        pass

    def unhotplug_qmp(self, device):
        pass


class RawFormat(QBaseFormat, ABC):
    def qemu_cmdline(self, device):
        params_cp = device.params.copy()
        if isinstance(device, QStringDevice):
            if device._cmdline:
                return device._cmdline % device.params
        else:
            if "backend" in params_cp.keys():
                out = "-%s %s," % (device.type, params_cp.get("backend"))
                del params_cp["backend"]
            else:
                out = "-%s " % device.type
            for key, value in params_cp.items():
                if value != "NO_EQUAL_STRING":
                    out += "%s=%s," % (key, value)
                else:
                    out += "%s," % key
            if out[-1] == ',':
                out = out[:-1]
            return out

    # (qemu) device_add virtio-blk-pci,drive=disk1,id=myvirtio1
    def hotplug_hmp(self, device):
        pass

    # device_del usbdisk1
    def unhotplug_hmp(self, device_id):
        pass


def get_devices_cmd(devices, qemu_cmd):
    for device in devices:
        if isinstance(device, list):
            qemu_cmd = get_devices_cmd(device, qemu_cmd)
        else:
            # the default format_class is RawFormat
            format_class = "RawFormat"
            for key, val in class_name_cmdl_fmt_mapping.items():
                if type(device).__name__ in val:
                    format_class = key
            tmp = eval(format_class)().qemu_cmdline(device)
            # if device.type not in qemu_ignore_option:
            #    tmp = device_representation(device)
            qemu_cmd += " " if qemu_cmd[-1] != " " else ""
            qemu_cmd += tmp if tmp else ""

    return qemu_cmd


def get_sub_devices_representation_by_root(devices=[], tag=None):
    """
    Generate the part of the devices representation based on tag.

    :params devices: the device object in list
    :type devices: list
    :params tag: the device tag
    :type tag: string
    :return: representation of qemu device based on tag
    :rtype: string
    """
    # if using tag, set tag should be done once the device being created.
    # nowhere for landing.
    pass


def get_each_devices_representation(qcon, cfg_name="libvirt-latest.json"):
    """
    Generate the whole qemu device representation based on
    the completed qemu device list.

    :params qcon: the qemu devices
    :type qcon: the DevContainer object
    :params cfg_name: the name of qemu_cmdline_format_cfg file
    :type cfg_name: string
    :return: the qemu device cmdline representation
    :rtype: string
    """
    if not qcon:
        return ""
    libvirt_ver = re.findall(r"libvirt.*\.json$", cfg_name)
    libvirt_ver = libvirt_ver[-1].replace(".json", "") if libvirt_ver else "libvirt-latest"

    # update the json_format_type_mapping
    _update_json_format_type_mapping(json_format_type_mapping,
                                     libvirt_version_diff_mapping[libvirt_ver])
    # traverse the qcon and generate the qemu commandline
    qemu_cmd = get_devices_cmd(qcon, " ")

    # if qemu_cmd[-1] == "\\":
    #     qemu_cmd = qemu_cmd.replace("\\", "", -1)
    return qemu_cmd


# todo: read .json file
class_name_cmdl_fmt_mapping = {
    "JsonFormat": ["Memory", "QBlockdevNode", "QDevice", "QObject",
                   "QBlockdevProtocolFile", "QBlockdevFormatQcow2",
                   "QBlockdevFormatNode", "QBlockdevFormatRaw",
                   "QBlockdevFormatLuks", "QBlockdevProtocol",
                   "QBlockdevProtocolNullCo", "QBlockdevProtocolHostDevice",
                   "QBlockdevProtocolBlkdebug", "QBlockdevProtocolHostCdrom",
                   "QBlockdevProtocolISCSI", "QBlockdevProtocolRBD",
                   "QBlockdevFilter", "QBlockdevFilterCOR",
                   "QBlockdevFilterThrottle", "QBlockdevProtocolGluster",
                   "QBlockdevProtocolNBD", "QBlockdevProtocolNVMe",
                   "QBlockdevProtocolSSH", "QBlockdevProtocolHTTP",
                   "QBlockdevProtocolHTTPS", "QBlockdevProtocolFTP",
                   "QBlockdevProtocolFTPS"]
}

json_format_type_mapping = {
    "device": {
        "scsi-hd": {
            "wwn": string_to_hexadecimal,
            "physical_block_size": string_to_decimal,
            "logical_block_size": string_to_decimal,
            "bootindex": string_to_decimal,
            "discard_granularity": string_to_decimal},
        "pcie-root-port": {
            "port": string_to_hexadecimal,
            "multifunction": string_to_boolean},
        "pvpanic": {
            "ioport": string_to_hexadecimal,
            "events": string_to_decimal},
        "virtio-scsi-pci": {
            "max_sectors": string_to_decimal,
            "num_queues": string_to_decimal,
            "virtqueue_size": string_to_decimal,
            "disable-legacy": string_to_boolean},
        "virtio-rng-pci": {
            "period": string_to_decimal,
            "max-bytes": string_to_decimal},
        "virtio-blk-pci": {
            "max-write-zeroes-sectors": string_to_decimal,
            "queue-size": string_to_decimal,
            "max-discard-sectors": string_to_decimal,
            "num-queues": string_to_decimal,
            "discard_granularity": string_to_decimal},
        "virtio-net-pci": {
            "host_mtu": string_to_decimal,
            "speed": string_to_decimal,
            "vectors": string_to_decimal,
            "acpi-index": string_to_decimal},
        "pc-dimm": {
            "node": string_to_decimal},
        "usb-storage": {
            "min_io_size": string_to_decimal,
            "opt_io_size": string_to_decimal,
            "removable": string_to_boolean,
            "serial": spec_type_to_string,
            "port": int_to_string},
        "usb-mouse": {
            "serial": spec_type_to_string,
            "port": int_to_string},
        "usb-kbd": {
            "serial": spec_type_to_string,
            "port": int_to_string},
        "usb-hub": {
            "serial": spec_type_to_string,
            "port": int_to_string},
        "usb-tablet": {
            "serial": spec_type_to_string,
            "port": int_to_string},
        "usb-ccid": {
            "serial": spec_type_to_string,
            "port": int_to_string},
        "usb-host": {
            "serial": spec_type_to_string,
            "port": int_to_string},
        "ich9-usb-ehci1": {
            "multifunction": string_to_boolean},
        "virtio-balloon-ccw": {
            "guest-stats-polling-interval": string_to_decimal},
        "virtio-mem-pci": {
            "requested-size": string_to_b_unit},
        "nvdimm": {
            "label-size": string_to_b_unit}},
    "blockdev": {
        "qcow2": {
            "cache-size": string_to_decimal,
            "cache.direct": string_to_boolean,
            "cache.no-flush": string_to_boolean,
            "auto-read-only": string_to_boolean,
            "read-only": string_to_boolean},
        "https": {
            "timeout": string_to_decimal,
            "cache.direct": string_to_boolean,
            "cache.no-flush": string_to_boolean,
            "auto-read-only": string_to_boolean,
            "read-only": string_to_boolean},
        "raw": {
            "cache.direct": string_to_boolean,
            "cache.no-flush": string_to_boolean,
            "auto-read-only": string_to_boolean,
            "read-only": string_to_boolean},
        "luks": {
            "cache.direct": string_to_boolean,
            "cache.no-flush": string_to_boolean,
            "auto-read-only": string_to_boolean,
            "read-only": string_to_boolean},
        "file": {
            "cache.direct": string_to_boolean,
            "cache.no-flush": string_to_boolean,
            "auto-read-only": string_to_boolean,
            "read-only": string_to_boolean},
        "null-co": {
            "cache.direct": string_to_boolean,
            "cache.no-flush": string_to_boolean,
            "auto-read-only": string_to_boolean,
            "read-only": string_to_boolean},
        "host_device": {
            "cache.direct": string_to_boolean,
            "cache.no-flush": string_to_boolean,
            "auto-read-only": string_to_boolean,
            "read-only": string_to_boolean},
        "blkdebug": {
            "cache.direct": string_to_boolean,
            "cache.no-flush": string_to_boolean,
            "auto-read-only": string_to_boolean,
            "read-only": string_to_boolean},
        "host_cdrom": {
            "cache.direct": string_to_boolean,
            "cache.no-flush": string_to_boolean,
            "auto-read-only": string_to_boolean,
            "read-only": string_to_boolean},
        "iscsi": {
            "cache.direct": string_to_boolean,
            "cache.no-flush": string_to_boolean,
            "auto-read-only": string_to_boolean,
            "read-only": string_to_boolean},
        "rbd": {
            "cache.direct": string_to_boolean,
            "cache.no-flush": string_to_boolean,
            "auto-read-only": string_to_boolean,
            "read-only": string_to_boolean},
        "copy-on-read": {
            "cache.direct": string_to_boolean,
            "cache.no-flush": string_to_boolean,
            "auto-read-only": string_to_boolean,
            "read-only": string_to_boolean},
        "throttle": {
            "cache.direct": string_to_boolean,
            "cache.no-flush": string_to_boolean,
            "auto-read-only": string_to_boolean,
            "read-only": string_to_boolean},
        "gluster": {
            "cache.direct": string_to_boolean,
            "cache.no-flush": string_to_boolean,
            "auto-read-only": string_to_boolean,
            "read-only": string_to_boolean},
        "nbd": {
            "cache.direct": string_to_boolean,
            "cache.no-flush": string_to_boolean,
            "auto-read-only": string_to_boolean,
            "read-only": string_to_boolean},
        "nvme": {
            "cache.direct": string_to_boolean,
            "cache.no-flush": string_to_boolean,
            "auto-read-only": string_to_boolean,
            "read-only": string_to_boolean},
        "ssh": {
            "cache.direct": string_to_boolean,
            "cache.no-flush": string_to_boolean,
            "auto-read-only": string_to_boolean,
            "read-only": string_to_boolean},
        "http": {
            "cache.direct": string_to_boolean,
            "cache.no-flush": string_to_boolean,
            "auto-read-only": string_to_boolean,
            "read-only": string_to_boolean},
        "ftp": {
            "cache.direct": string_to_boolean,
            "cache.no-flush": string_to_boolean,
            "auto-read-only": string_to_boolean,
            "read-only": string_to_boolean},
        "ftps": {
            "cache.direct": string_to_boolean,
            "cache.no-flush": string_to_boolean,
            "auto-read-only": string_to_boolean,
            "read-only": string_to_boolean}},
    "object": {
        "memory-backend-memfd": {
            "share": string_to_boolean,
            "reserve": string_to_boolean,
            "size": string_to_b_unit,
            "hugetlb": string_to_boolean,
            "prealloc": string_to_boolean,
            "dump": string_to_boolean,
            "merge": string_to_boolean,
            "host-nodes": string_to_int_list,
            "discard-data": string_to_boolean},
        "memory-backend-ram": {
            "size": string_to_b_unit,
            "share": string_to_boolean,
            "reserve": string_to_boolean,
            "prealloc": string_to_boolean,
            "dump": string_to_boolean,
            "merge": string_to_boolean,
            "host-nodes": string_to_int_list,
            "discard-data": string_to_boolean},
        "memory-backend-file": {
            "size": string_to_b_unit,
            "align": string_to_b_unit,
            "share": string_to_boolean,
            "reserve": string_to_boolean,
            "pmem": string_to_boolean,
            "prealloc": string_to_boolean,
            "dump": string_to_boolean,
            "merge": string_to_boolean,
            "readonly": string_to_boolean,
            "host-nodes": string_to_int_list,
            "discard-data": string_to_boolean}}
}
# todo: qemu version
libvirt_version_diff_mapping = {
    "libvirt-latest": {
        "device": {
            "scsi-hd": {}}},
    "libvirt.6.0": {},
    "libvirt.8.0": {},
    "libvirt.8.3": {}
}

# qemu_ignore_option = ("vtpm")
