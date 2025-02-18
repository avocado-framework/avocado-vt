import logging
import re

from avocado.utils import process

from virttest import utils_numeric

LOG = logging.getLogger("avocado." + __name__)


class _QDeviceFormatManagement(object):
    """
    This class is designed to manage the expression( including json format
    and raw format) of classes in qdevices.py file.
    """

    qemu_binary = None

    def __init__(self):
        self._format_func = {"json": self._json_format, "raw": self._raw_format}
        # _special_args_in_json stores the common qemu device type.
        # For examples:
        #   -blockdev xxx,xxx
        #   -device xxx,xxx
        #   -object xxx,xxx
        # Those qemu device types except -device have the following structure:
        #   "${qemu_device_type}": {
        #       "${argument#01}": ${type_in_json_format},
        #       "${argument#02}": ${type_in_json_format},
        #       ...
        #   }
        # The -device has the following structure:
        #   "${qemu_device_type}": {
        #       "${driver#01}": {
        #           "${argument#01}": ${type_in_json_format},
        #           "${argument#02}": ${type_in_json_format},
        #           ...
        #       },
        #       "${driver#02}": {
        #           "${argument#01}": ${type_in_json_format},
        #           "${argument#02}": ${type_in_json_format},
        #           ...
        #       },
        #       ...
        #   }
        # NOTE:
        #   1. The records are from collections at qdevices.py
        #   2. For arguments type conversion from string( on/off, yes/on,
        #      true/false ) to bool( True/False ), they are NOT listed here
        #      since they are too many.
        self._special_args_in_json = {
            "blockdev": {
                "detect-zeroes": self._unchanged,
                "offset": self._str_to_dec,
                "size": self._str_to_dec,
                "cache-size": self._str_to_dec,
                "timeout": self._str_to_dec,
            },
            "device": {
                # "general" is NOT a kind of driver.
                # The arguments in "general" are needed by
                # at least 2 drivers.
                "general": {
                    "write-cache": self._unchanged,
                    "disable-legacy": self._unchanged,
                    "serial": self._unchanged,
                },
                "virtio-scsi-pci": {
                    "virtqueue_size": self._str_to_dec,
                    "num_queues": self._str_to_dec,
                    "max_sectors": self._str_to_dec,
                },
                "virtio-rng-pci": {
                    "period": self._str_to_dec,
                    "max-bytes": self._str_to_dec,
                },
                "scsi-hd": {
                    "discard_granularity": self._str_to_dec,
                    "physical_block_size": self._str_to_dec,
                    "logical_block_size": self._str_to_dec,
                    "bootindex": self._str_to_dec,
                },
                "virtio-blk-pci": {
                    "max-write-zeroes-sectors": self._str_to_dec,
                    "queue-size": self._str_to_dec,
                    "max-discard-sectors": self._str_to_dec,
                    "num-queues": self._str_to_dec,
                    "discard_granularity": self._str_to_dec,
                    "physical_block_size": self._str_to_dec,
                    "logical_block_size": self._str_to_dec,
                },
                "usb_driver": {
                    "port": self._str,
                    "serial": self._on,
                    # min_io_size, opt_io_size from device ("driver": "usb-storage")
                    "min_io_size": self._str_to_dec,
                    "opt_io_size": self._str_to_dec,
                },
                "pcie-root-port": {
                    "port": self._hex_in_str_to_dec,
                },
                "nvdimm": {
                    "label-size": self._normalize_data_size,
                },
                "pc-dimm": {
                    "node": self._str_to_dec,
                    "addr": self._hex_in_str_to_dec,
                },
                "virtio-mem-pci": {
                    "requested-size": self._normalize_data_size,
                },
                "intel-iommu": {
                    "aw-bits": self._str_to_dec,
                    "wwn": self._hex_in_str_to_dec,
                    "eim": self._unchanged,
                    "intremap": self._unchanged,
                },
                "virtio-net-pci": {
                    "acpi-index": self._str_to_dec,
                    "host_mtu": self._str_to_dec,
                    "speed": self._str_to_dec,
                    "vectors": self._str_to_dec,
                },
                "virtio-balloon-ccw": {
                    "guest-stats-polling-interval": self._str_to_dec,
                },
                "virtio-balloon-pci": {
                    "guest-stats-polling-interval": self._str_to_dec,
                },
                "pvpanic": {
                    "events": self._str_to_dec,
                },
            },
            "object": {
                "size": self._normalize_data_size,
                "align": self._normalize_data_size,
                "host-nodes": self._int_in_list,
                "prealloc-threads": self._str_to_dec,
            },
            "netdev": {
                "fd": self._unchanged,
                "vhostfd": self._unchanged,
                "dnssearch": self._dict_in_list,
                "hostfwd": self._dict_in_list,
                "guestfwd": self._dict_in_list,
                "sndbuf": self._normalize_data_size,
            },
        }
        self._device_driver_checked = []
        # _skip_args stores those arguments which are NOT expected to be
        # converted while updating the arguments type from qemu on machine.
        #   About "addr" in qemu output,
        #       addr=<int32> - Slot and optional function number, example: 06.0 or 06 (default: -1)
        #   In fact: The "addr" is accepted by hexadecimal in string instead of
        #   hexadecimal in int.
        #   The following is qemu output:
        #   qemu-kvm: -device {"id": "pcie-root-port-0", "driver": "pcie-root-port",
        #   "multifunction": true, "bus": "pcie.0", "addr": 1,
        #   "chassis": 1}: PCI: single function device can't be populated in function 0.1
        self._skip_args = ("addr",)
        # _mandatory_assignment_args_type stores those arguments whose types
        # are assigned. The _mandatory_assignment_args_type structure is as
        # same as the _special_args_in_json structure.
        self._mandatory_assignment_args_type = {
            "device": {
                "pvpanic": {
                    #   About "ioport" in qemu output:
                    #       ioport=<uint16>        -  (default: 1285)
                    #   In fact: The "ioport" is accepted by function
                    #   _hex_in_str_to_dec instead of function _str_to_dec.
                    "ioport": self._hex_in_str_to_dec,
                },
                "vhost-vsock-pci": {
                    #   About "guest-cid" in qemu output:
                    #       guest-cid=<uint64>     -  (default: 0)
                    #   In fact: The "guest-cid" is accepted by function
                    #   _str_to_dec instead of function _hex_in_str_to_dec.
                    "guest-cid": self._str_to_dec,
                },
                "vhost-vsock-ccw": {
                    #   About "guest-cid" in qemu output:
                    #       guest-cid=<uint64>     -  (default: 0)
                    #   In fact: The "guest-cid" is accepted by function
                    #   _str_to_dec instead of function _hex_in_str_to_dec.
                    "guest-cid": self._str_to_dec,
                },
            }
        }
        self._type_func_mapping = {
            "<int16>": self._str_to_dec,
            "<uint16>": self._str_to_dec,
            "<int32>": self._str_to_dec,
            "<uint32>": self._str_to_dec,
            "<bool>": self._bool_in_string_to_bool,
            "<int64>": self._hex_in_str_to_dec,
            "<uint64>": self._hex_in_str_to_dec,
            "<str>": self._str,
        }

    def format(self, format_type, params, dev_type):
        """
        Convert the params format based on format_type and dev_type.

        :param format_type: The expected format.
        :type format_type: String.
        :param params: The params.
        :type params: Dict.
        :param dev_type: The device type.
        :type dev_type: String.

        :return: The params in the expected format.
        :rtype: Dict.
        """
        return self._format_func[format_type](params, dev_type)

    def _json_format(self, params, dev_type):
        """
        Convert the params to json format based on dev_type.

        :param params: The params.
        :type params: Dict.
        :param dev_type: The device type.
        :type dev_type: String.

        :return: The params in the json format.
        :rtype: Dict.
        """
        return eval("self._" + dev_type + "_json_format")(params)

    def _raw_format(self, params, dev_type):
        """
        Convert the params to raw format based on dev_type.

        :param params: The params.
        :type params: Dict.
        :param dev_type: The device type.
        :type dev_type: String.

        :return: The params in the raw format.
        :rtype: Dict.
        """
        # TODO:
        #   Implement this function and replace the related functions in
        #   qdevices.py file
        pass

    def _netdev_json_format(self, params):
        """
        Convert the params to json format based on the netdev.

        :param params: The params.
        :type params: Dict.

        :return: The params in the json format.
        :rtype: Dict.
        """
        dev_type = "netdev"
        args_in_json = self._special_args_in_json[dev_type]
        new_args = dict()
        for key, value in params.items():
            if key in args_in_json.keys():
                new_args[key] = args_in_json[key](value)
            elif isinstance(value, str) and value.isdigit():
                new_args[key] = int(value)
            else:
                new_args[key] = self._bool_in_string_to_bool(value)

            if "." in key:
                new_args = self._flat_to_dict(key, new_args)

        return new_args

    def _object_json_format(self, params):
        """
        Convert the params to json format based on the object.

        :param params: The params.
        :type params: Dict.

        :return: The params in the json format.
        :rtype: Dict.
        """
        dev_type = "object"
        params = params.copy()
        if "backend" in params:
            params["qom-type"] = params.pop("backend")
        args_in_json = self._special_args_in_json[dev_type]
        new_args = dict()
        for key, value in params.items():
            if key in args_in_json.keys():
                new_args[key] = args_in_json[key](value)
            else:
                new_args[key] = self._bool_in_string_to_bool(value)

        return new_args

    def _device_json_format(self, params):
        """
        Convert the params to json format based on the device.

        :param params: The params.
        :type params: Dict.

        :return: The params in the json format.
        :rtype: Dict.
        """
        dev_type = "device"
        driver = params.get("driver")
        driver = "usb_driver" if driver.startswith("usb-") else driver
        if driver not in self._device_driver_checked:
            self._device_driver_checked.append(driver)
            if self.qemu_binary:
                self._update_args_type_from_qemu(driver)
        device_args = self._special_args_in_json[dev_type]
        new_args = dict()
        # convert type
        for key, value in params.items():
            if key in device_args[driver]:
                value = device_args[driver][key](value)
                new_args[key] = value
                if device_args[driver][key].__name__ is self._unchanged.__name__:
                    continue

            if key in device_args["general"]:
                new_args[key] = device_args["general"][key](value)
            else:
                new_args[key] = self._bool_in_string_to_bool(value)

        return new_args

    def _blockdev_json_format(self, params):
        """
        Convert the params to json format based on the blockdev.

        :param params: The params.
        :type params: Dict.

        :return: The params in the json format.
        :rtype: Dict.
        """
        dev_type = "blockdev"
        args_in_json = self._special_args_in_json[dev_type]
        new_args = dict()
        for key, value in params.items():
            new_args[key] = (
                args_in_json[key](value)
                if key in args_in_json.keys()
                else self._bool_in_string_to_bool(value)
            )
            if "." in key:
                new_args = self._flat_to_dict(key, new_args)

        return new_args

    @staticmethod
    def _unchanged(val):
        """
        Do NOT change anything, just return the val.

        :param val: The value.
        :type val: Any

        :return: The value.
        :rtype: Any
        """
        return val

    @staticmethod
    def _str_to_dec(val):
        """
        Convert decimal in string to int.

        :param val: The value.
        :type val: String

        :return: The value.
        :rtype: int
        """
        return int(val)

    @staticmethod
    def _str(val):
        """
        Convert any type to string.

        :param val: The value.
        :type val: Any

        :return: The value.
        :rtype: String
        """
        return str(val)

    @staticmethod
    def _on(val):
        """
        Convert "NO_EQUAL_STRING" to "on".

        :param val: The value.
        :type val: String

        :return: The value.
        :rtype: String
        """
        return "on" if val == "NO_EQUAL_STRING" else val

    @staticmethod
    def _hex_in_str_to_dec(val):
        """
        Convert hexadecimal in string to int.

        :param val: The value.
        :type val: String

        :return: The value.
        :rtype: int
        """
        if isinstance(val, str) and val.startswith("0x"):
            val = val[2:]
        return int(val, 16)

    @staticmethod
    def _normalize_data_size(val):
        """
        Normalize a data size based on the magnitude bytes.

        :param val: The value.
        :type val: String

        :return: The value.
        :rtype: int
        """
        if isinstance(val, str):
            return int(utils_numeric.normalize_data_size(val, "B"))
        return val

    @staticmethod
    def _int_in_list(val):
        """
        Converted string to int in list.

        :param val: The value.
        :type val: String

        :return: The value.
        :rtype: list
        """
        return list(map(int, val.split()))

    @staticmethod
    def _dict_in_list(val):
        """
        Converted list to dict in list.

        :param val: The value.
        :type val: list

        :return: The value.
        :rtype: list
        """
        if isinstance(val, list):
            return [{"str": v} for v in val]
        return val

    @staticmethod
    def _bool_in_string_to_bool(val):
        """
        Convert the "on""off""yes""no""true""false" to boolean.
        Note: If the val is a string except "on""off""yes""no""true""false",
                just return val without any operations.

        :param val: The value.
        :type val: String.

        :return: The value converted or original val.
        :rtype: Boolean or the original type.
        """
        if isinstance(val, str) and val.lower() in (
            "on",
            "off",
            "yes",
            "no",
            "true",
            "false",
        ):
            return val in (
                "on",
                "yes",
                "true",
            )
        return val

    @staticmethod
    def _flat_to_dict(key, args):
        """
        Convert the flat expression to multi-level expression.

        :param key: The flat key.
        :type key: String.
        :param args: The structure including flat key.
        :type args: Dict.

        :return: The structure converted.
        :rtype: Dict.
        """
        val = args[key]
        parts = key.split(".")
        if parts:
            args.pop(key)
        p = re.compile(r"(?P<man>.+)\.(?P<index>\d+)(\.(?P<opt>.+))?")
        m = p.match(key)
        if m:
            # convert 'server.0.host=xx', 'server.1.host=yy'
            # to {'server': [{'host':xx}, {'host':yy}]}
            # OR
            # convert 'port.0=xxx', 'port.1=yyy'
            # to {'port': ['xxx', 'yyy']}
            # OR
            # convert 'port.0.a'='a', 'port.0.b'='b'
            # to {'port': [{'a': 'a', 'b': 'y'}]}
            man = m.group("man")
            index = int(m.group("index"))
            opt = m.group("opt")
            args[man] = args[man] if man in args else []
            if opt:
                if index < len(args[man]):
                    args[man][index][opt] = val
                else:
                    args[man].insert(index, {opt: val})
            else:
                args[man].insert(index, val)
        else:
            # convert 'cache.direct': 'true' to {'cache': {'direct': 'true'}}
            tmp = args
            for part in parts[:-1]:
                if part not in tmp:
                    tmp[part] = dict()
                tmp = tmp[part]
            tmp[parts[-1]] = val

        return args

    def _update_args_type_from_qemu(self, driver):
        """
        Update the args type from qemu.
        Only update the following type: int16, int32, int64, bool, str.

        :param driver: The driver of -device.
        :type driver: String.
        """
        if driver not in self._special_args_in_json["device"]:
            self._special_args_in_json["device"][driver] = dict()
        cmd = "%s --device %s,\\?" % (self.qemu_binary, driver)
        output = process.run(cmd, shell=True, verbose=False).stdout_text.strip()
        args_list = re.findall("(.+)=(<[^>]+>+)", output)
        for arg, arg_type in args_list:
            arg = arg.strip()
            if arg in self._skip_args:
                continue
            arg_type = arg_type.strip()
            if driver not in self._mandatory_assignment_args_type["device"]:
                self._mandatory_assignment_args_type["device"][driver] = dict()
            if arg in self._mandatory_assignment_args_type["device"][driver]:
                self._special_args_in_json["device"][driver][arg] = (
                    self._mandatory_assignment_args_type["device"][driver][arg]
                )
            elif arg_type in self._type_func_mapping:
                self._special_args_in_json["device"][driver][arg] = (
                    self._type_func_mapping[arg_type]
                )


qdevice_format = _QDeviceFormatManagement()
