"""
Shared classes and functions (exceptions, ...)

:copyright: 2013 Red Hat Inc.
"""

import six


#
# Exceptions
#
class DeviceError(Exception):
    """General device exception"""

    pass


class DeviceInsertError(DeviceError):
    """Fail to insert device"""

    def __init__(self, device, reason, vmdev):
        self.device = device
        self.reason = reason
        self.vmdev = vmdev
        self.issue = "insert"

    def __str__(self):
        return (
            "Failed to %s device:\n%s\nBecause:\n%s\nList of VM devices:\n"
            "%s\n%s"
            % (
                self.issue,
                self.device.str_long(),
                self.reason,
                self.vmdev.str_short(),
                self.vmdev.str_bus_long(),
            )
        )


class DeviceRemoveError(DeviceInsertError):
    """Fail to remove device"""

    def __init__(self, device, reason, vmdev):
        DeviceInsertError.__init__(self, device, reason, vmdev)
        self.issue = "remove"


class DeviceHotplugError(DeviceInsertError):
    """Fail to hotplug device"""

    def __init__(self, device, reason, vmdev, ver_out=None):
        DeviceInsertError.__init__(self, device, reason, vmdev)
        self.issue = "hotplug"
        self.ver_out = ver_out  # Output of device.verify_hotplug (optionally)


class DeviceUnplugError(DeviceHotplugError):
    """Fail to unplug device"""

    def __init__(self, device, reason, vmdev):
        DeviceHotplugError.__init__(self, device, reason, vmdev)
        self.issue = "unplug"


#
# Utilities
#
def none_or_int(value):
    """Helper function which returns None or int()"""
    if isinstance(value, int):
        return value
    elif not value:  # "", None, False
        return None
    elif isinstance(value, six.string_types) and value.isdigit():
        return int(value)
    else:
        raise TypeError("This parameter has to be int or none")


def set_cmdline_format_by_cfg(dev, config, key):
    """
    Mark the cmdline format based on the settings.

    :param dev: The device needed to be marked
    :param config: Dict with setting
    :param key: The field of device
    """
    if key in config:
        name = dev.type
        if name in config[key]:
            dev.cmdline_format = config[key][name]
