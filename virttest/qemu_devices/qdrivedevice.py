"""
Autotest representation of qemu qdrive devices.

These classes implements various features in order to simulate, verify or
interact with qemu qdev structure.

:copyright: 2012-2013 Red Hat Inc.
"""
# Python imports
import logging
import re

# Autotest imports
from utils import DeviceError
from virttest import qemu_monitor
from virttest.qemu_devices.qdevices import QCustomDevice
from virttest.qemu_devices import qbuses


def _convert_args(arg_dict):
    """
    Convert monitor command arguments dict into humanmonitor string.

    :param arg_dict: The dict of monitor command arguments.
    :return: A string in humanmonitor's 'key=value' format, or a empty
             '' when the dict is empty.
    """
    return ",".join("%s=%s" % (key, val) for key, val in arg_dict.iteritems())


class QDrive(QCustomDevice):

    """
    Representation of the '-drive' qemu object without hotplug support.
    """

    def __init__(self, aobject, use_device=True):
        child_bus = qbuses.QDriveBus('drive_%s' % aobject, aobject)
        super(QDrive, self).__init__("drive", {}, aobject, (),
                                     child_bus)
        if use_device:
            self.params['id'] = 'drive_%s' % aobject

    def set_param(self, option, value, option_type=None):
        """
        Set device param using qemu notation ("on", "off" instead of bool...)
        It restricts setting of the 'id' param as it's automatically created.
        :param option: which option's value to set
        :param value: new value
        :param option_type: type of the option (bool)
        """
        if option == 'id':
            raise KeyError("Drive ID is automatically created from aobject. %s"
                           % self)
        elif option == 'bus':
            # Workaround inconsistency between -drive and -device
            value = re.findall(r'(\d+)', value)
            if value is not None:
                value = value[0]
        super(QDrive, self).set_param(option, value, option_type)


class QOldDrive(QDrive):

    """
    This is a variant for -drive without 'addr' support
    """

    def set_param(self, option, value, option_type=None):
        """
        Ignore addr parameters as they are not supported by old qemus
        """
        if option == 'addr':
            logging.warn("Ignoring 'addr=%s' parameter of %s due of old qemu"
                         ", PCI addresses might be messed up.", value,
                         self.str_short())
            return
        return super(QOldDrive, self).set_param(option, value, option_type)


class QHPDrive(QDrive):

    """
    Representation of the '-drive' qemu object with hotplug support.
    """

    def __init__(self, aobject):
        super(QHPDrive, self).__init__(aobject)
        self.__hook_drive_bus = None

    def verify_hotplug(self, out, monitor):
        if isinstance(monitor, qemu_monitor.QMPMonitor):
            if out.startswith('OK'):
                return True
        else:
            if out == 'OK':
                return True
        return False

    def verify_unplug(self, out, monitor):
        out = monitor.info("qtree", debug=False)
        if "unknown command" in out:       # Old qemu don't have info qtree
            return True
        dev_id_name = 'id "%s"' % self.aid
        if dev_id_name in out:
            return False
        else:
            return True

    def get_children(self):
        """ Device bus should be removed too """
        for bus in self.child_bus:
            if isinstance(bus, qbuses.QDriveBus):
                drive_bus = bus
                self.rm_child_bus(bus)
                break
        devices = super(QHPDrive, self).get_children()
        self.add_child_bus(drive_bus)
        return devices

    def unplug_hook(self):
        """
        Devices from this bus are not removed, only 'drive' is set to None.
        """
        for bus in self.child_bus:
            if isinstance(bus, qbuses.QDriveBus):
                for dev in bus:
                    self.__hook_drive_bus = dev.get_param('drive')
                    dev['drive'] = None
                break

    def unplug_unhook(self):
        """ Set back the previous 'drive' (unsafe, using the last value) """
        if self.__hook_drive_bus is not None:
            for bus in self.child_bus:
                if isinstance(bus, qbuses.QDriveBus):
                    for dev in bus:
                        dev['drive'] = self.__hook_drive_bus
                    break

    def hotplug_hmp(self):
        """ :return: the hotplug monitor command """
        args = self.params.copy()
        pci_addr = args.pop('addr', 'auto')
        args = _convert_args(args)
        return "drive_add %s %s" % (pci_addr, args)

    def unplug_hmp(self):
        """ :return: the unplug monitor command """
        if self.get_qid() is None:
            raise DeviceError("qid not set; device %s can't be unplugged"
                              % self)
        return "drive_del %s" % self.get_qid()


class QRHDrive(QDrive):

    """
    Representation of the '-drive' qemu object with RedHat hotplug support.
    """

    def __init__(self, aobject):
        super(QRHDrive, self).__init__(aobject)
        self.__hook_drive_bus = None

    def hotplug_hmp(self):
        """ :return: the hotplug monitor command """
        args = self.params.copy()
        args.pop('addr', None)    # not supported by RHDrive
        args.pop('if', None)
        args = _convert_args(args)
        return "__com.redhat_drive_add %s" % args

    def hotplug_qmp(self):
        """ :return: the hotplug monitor command """
        args = self.params.copy()
        args.pop('addr', None)    # not supported by RHDrive
        args.pop('if', None)
        return "__com.redhat_drive_add", args

    def get_children(self):
        """ Device bus should be removed too """
        for bus in self.child_bus:
            if isinstance(bus, qbuses.QDriveBus):
                drive_bus = bus
                self.rm_child_bus(bus)
                break
        devices = super(QRHDrive, self).get_children()
        self.add_child_bus(drive_bus)
        return devices

    def unplug_hook(self):
        """
        Devices from this bus are not removed, only 'drive' is set to None.
        """
        for bus in self.child_bus:
            if isinstance(bus, qbuses.QDriveBus):
                for dev in bus:
                    self.__hook_drive_bus = dev.get_param('drive')
                    dev['drive'] = None
                break

    def unplug_unhook(self):
        """ Set back the previous 'drive' (unsafe, using the last value) """
        if self.__hook_drive_bus is not None:
            for bus in self.child_bus:
                if isinstance(bus, qbuses.QDriveBus):
                    for dev in bus:
                        dev['drive'] = self.__hook_drive_bus
                    break

    def unplug_hmp(self):
        """ :return: the unplug monitor command """
        if self.get_qid() is None:
            raise DeviceError("qid not set; device %s can't be unplugged"
                              % self)
        return "__com.redhat_drive_del %s" % self.get_qid()

    def unplug_qmp(self):
        """ :return: the unplug monitor command """
        if self.get_qid() is None:
            raise DeviceError("qid not set; device %s can't be unplugged"
                              % self)
        return "__com.redhat_drive_del", {'id': self.get_qid()}
