"""
Autotest representation of qemu devices.

These classes implements various features in order to simulate, verify or
interact with qemu qdev structure.

:copyright: 2012-2013 Red Hat Inc.
"""
import logging
import os
import time
import re
import traceback
from collections import OrderedDict

import aexpect

from virttest import qemu_monitor
from virttest import utils_misc
from virttest import utils_qemu
from virttest.qemu_devices.utils import DeviceError
from virttest.qemu_devices.utils import none_or_int
from virttest.utils_version import VersionInterval

import six
from six.moves import xrange

LOG = logging.getLogger('avocado.' + __name__)


def _convert_args(arg_dict):
    """
    Convert monitor command arguments dict into humanmonitor string.

    :param arg_dict: The dict of monitor command arguments.
    :return: A string in humanmonitor's 'key=value' format, or a empty
             '' when the dict is empty.
    """
    return ",".join("%s=%s" % (key, val) for key, val in six.iteritems(arg_dict))


def _build_cmd(cmd, args=None, q_id=None):
    """
    Format QMP command from cmd and args

    :param cmd: Command ('device_add', ...)
    :param q_id: queue id; True = generate random, None = None, str = use str
    """
    obj = {"execute": cmd}
    if args is not None:
        obj["arguments"] = args
    if q_id is True:
        obj["id"] = utils_misc.generate_random_string(8)
    elif q_id is not None:
        obj["id"] = q_id
    return obj


#
# Device objects
#
class QBaseDevice(object):

    """ Base class of qemu objects """

    def __init__(self, dev_type="QBaseDevice", params=None, aobject=None,
                 parent_bus=None, child_bus=None):
        """
        :param dev_type: type of this component
        :param params: component's parameters
        :param aobject: Autotest object which is associated with this device
        :param parent_bus: list of dicts specifying the parent bus
        :param child_bus: list of buses, which this device provides
        """
        self.aid = None         # unique per VM id
        self.type = dev_type    # device type
        self.aobject = aobject  # related autotest object
        if parent_bus is None:
            parent_bus = tuple()
        self.parent_bus = parent_bus   # list of buses into which this dev fits
        self.child_bus = []            # list of buses which this dev provides
        if child_bus is None:
            child_bus = []
        elif not isinstance(child_bus, (list, tuple)):
            self.add_child_bus(child_bus)
        else:
            for bus in child_bus:
                self.add_child_bus(bus)
        self.dynamic_params = []
        self.params = OrderedDict()    # various device params (id, name, ...)
        if params:
            for key, value in six.iteritems(params):
                self.set_param(key, value)

    def add_child_bus(self, bus):
        """
        Add child bus
        :param bus: Bus, which this device contains
        :type bus: QSparseBus-like
        """
        self.child_bus.append(bus)
        bus.set_device(self)

    def rm_child_bus(self, bus):
        """
        removes child bus
        :param bus: Bus, which this device contains
        :type bus: QSparseBus-like
        """
        self.child_bus.remove(bus)
        bus.set_device(None)

    def set_param(self, option, value, option_type=None, dynamic=False):
        """
        Set device param using qemu notation ("on", "off" instead of bool...)
        :param option: which option's value to set
        :param value: new value
        :param option_type: type of the option (bool)
        :param dynamic: if true value is changed to DYN for not_dynamic compare
        """
        if dynamic:
            if option not in self.dynamic_params:
                self.dynamic_params.append(option)
        else:
            if option in self.dynamic_params:
                self.dynamic_params.remove(option)

        if option_type is bool or isinstance(value, bool):
            if value in ['yes', 'on', True]:
                self.params[option] = "on"
            elif value in ['no', 'off', False]:
                self.params[option] = "off"
        elif value or value == 0:
            if value == "EMPTY_STRING":
                self.params[option] = '""'
            else:
                self.params[option] = value
        elif value is None and option in self.params:
            del(self.params[option])
            if option in self.dynamic_params:
                self.dynamic_params.remove(option)

    def get_param(self, option, default=None):
        """ :return: object param """
        return self.params.get(option, default)

    def __getitem__(self, option):
        """ :return: object param """
        return self.params[option]

    def __delitem__(self, option):
        """ deletes self.params[option] """
        del(self.params[option])

    def __len__(self):
        """ length of self.params """
        return len(self.params)

    def __setitem__(self, option, value):
        """ self.set_param(option, value, None) """
        return self.set_param(option, value)

    def __contains__(self, option):
        """ Is the option set? """
        return option in self.params

    def __str__(self):
        """ :return: Short string representation of this object. """
        return self.str_short()

    def __eq__(self, dev2, dynamic=True):
        """ :return: True when devs are similar, False when different. """
        if not isinstance(dev2, QBaseDevice):
            return False
        check_attrs = ['cmdline_nd', 'hotplug_hmp_nd', 'hotplug_qmp_nd']
        try:
            for check_attr in check_attrs:
                try:
                    _ = getattr(self, check_attr)()
                except (DeviceError, NotImplementedError, AttributeError):
                    try:
                        getattr(dev2, check_attr)()
                    except (DeviceError, NotImplementedError, AttributeError):
                        pass
                else:
                    if _ != getattr(dev2, check_attr)():
                        return False
        except Exception:
            LOG.error(traceback.format_exc())
            return False
        return True

    def __ne__(self, dev2):
        """ :return: True when devs are different, False when similar. """
        return not self.__eq__(dev2)

    def str_short(self):
        """ Short representation (aid, qid, alternative, type) """
        if self.get_qid():  # Show aid only when it's based on qid
            if self.get_aid():
                return self.get_aid()
            else:
                return "q'%s'" % self.get_qid()
        elif self._get_alternative_name():
            return "a'%s'" % self._get_alternative_name()
        else:
            return "t'%s'" % self.type

    def str_long(self):
        """ Full representation, multi-line with all params """
        out = """%s
  aid = %s
  aobject = %s
  parent_bus = %s
  child_bus = %s
  params:""" % (self.type, self.aid, self.aobject, self.parent_bus,
                self.child_bus)
        for key, value in six.iteritems(self.params):
            out += "\n    %s = %s" % (key, value)
        return out + '\n'

    def _get_alternative_name(self):
        """ :return: alternative object name """
        return None

    def get_qid(self):
        """ :return: qemu_id """
        return self.params.get('id', '')

    def get_aid(self):
        """ :return: per VM unique autotest_id """
        return self.aid

    def set_aid(self, aid):
        """:param aid: new autotest id for this device"""
        self.aid = aid

    def get_children(self):
        """ :return: List of all children (recursive) """
        children = []
        for bus in self.child_bus:
            children.extend(bus)
        return children

    def cmdline(self):
        """ :return: cmdline command to define this device """
        raise NotImplementedError

    def cmdline_nd(self):
        """
        Command line without dynamic params.

        :return: cmdline command to define this device
                 without dynamic parameters
        """
        return self.cmdline()

    def _hotplug_qmp_mapping(self, qemu_version):
        """
        hotplug qmp command might change in new qemu release,
        this function is used to get the correct hotplug_qmp
        function object as per qemu version.

        :param qemu_version: The qemu version, e.g. 5.0.0
        :return: The hotplug_qmp function object
        """
        return self.hotplug_qmp

    def hotplug(self, monitor, qemu_version):
        """ :return: the output of monitor.cmd() hotplug command """
        if isinstance(monitor, qemu_monitor.QMPMonitor):
            try:
                cmd, args = self._hotplug_qmp_mapping(qemu_version)()
                return monitor.cmd(cmd, args)
            except DeviceError:     # qmp command not supported
                return monitor.human_monitor_cmd(self.hotplug_hmp())
        elif isinstance(monitor, qemu_monitor.HumanMonitor):
            return monitor.cmd(self.hotplug_hmp())
        else:
            raise TypeError("Invalid monitor object: %s(%s)" % (monitor,
                                                                type(monitor)))

    def hotplug_hmp(self):
        """ :return: the hotplug monitor command """
        raise DeviceError("Hotplug is not supported by this device %s", self)

    def hotplug_qmp(self):
        """ :return: tuple(hotplug qemu command, arguments)"""
        raise DeviceError("Hotplug is not supported by this device %s", self)

    def unplug_hook(self):
        """ Modification prior to unplug can be made here """
        pass

    def unplug_unhook(self):
        """ Roll back the modification made before unplug """
        pass

    def unplug(self, monitor):
        """ :return: the output of monitor.cmd() unplug command """
        if isinstance(monitor, qemu_monitor.QMPMonitor):
            try:
                cmd, args = self.unplug_qmp()
                return monitor.cmd(cmd, args)
            except DeviceError:     # qmp command not supported
                return monitor.human_monitor_cmd(self.unplug_hmp())
        elif isinstance(monitor, qemu_monitor.HumanMonitor):
            return monitor.cmd(self.unplug_hmp())
        else:
            raise TypeError("Invalid monitor object: %s(%s)" % (monitor,
                                                                type(monitor)))

    def unplug_hmp(self):
        """ :return: the unplug monitor command """
        raise DeviceError("Unplug is not supported by this device %s", self)

    def unplug_qmp(self):
        """ :return: tuple(unplug qemu command, arguments)"""
        raise DeviceError("Unplug is not supported by this device %s", self)

    def verify_hotplug(self, out, monitor):
        """
        :param out: Output of the hotplug command
        :param monitor: Monitor used for hotplug
        :return: True when successful, False when unsuccessful, string/None
                 when can't decide.
        """
        return out

    def verify_unplug(self, out, monitor):      # pylint: disable=W0613,R0201
        """
        :param out: Output of the unplug command
        :param monitor: Monitor used for unplug
        """
        return out

    def is_pcie_device(self):
        """Check is it a pcie device"""
        driver = self.get_param("driver", "")
        pcie_drivers = ["e1000e", "vhost-vsock-pci", "qemu-xhci", "vfio-pci",
                        "vhost-user-fs-pci"]
        return (driver in pcie_drivers or driver.startswith("virtio-"))


class QStringDevice(QBaseDevice):

    """
    General device which allows to specify methods by fixed or parametrizable
    strings in this format:

    ::

        "%(type)s,id=%(id)s,addr=%(addr)s"

    ``params`` will be used to subst ``%()s``
    """

    def __init__(self, dev_type="dummy", params=None, aobject=None,
                 parent_bus=None, child_bus=None, cmdline="", cmdline_nd=None):
        """
        :param dev_type: type of this component
        :param params: component's parameters
        :param aobject: Autotest object which is associated with this device
        :param parent_bus: bus(es), in which this device is plugged in
        :param child_bus: bus, which this device provides
        :param cmdline: cmdline string
        """
        super(QStringDevice, self).__init__(dev_type, params, aobject,
                                            parent_bus, child_bus)
        self._cmdline = cmdline
        self._cmdline_nd = cmdline_nd
        if cmdline_nd is None:
            self._cmdline_nd = cmdline

    def cmdline(self):
        """ :return: cmdline command to define this device """
        try:
            if self._cmdline:
                return self._cmdline % self.params
        except KeyError as details:
            raise KeyError("Param %s required for cmdline is not present in %s"
                           % (details, self.str_long()))

    def cmdline_nd(self):
        """
        Command line without dynamic parameters.

        :return: cmdline command to define this device without dynamic parameters.
        """
        try:
            if self._cmdline_nd:
                return self._cmdline_nd % self.params
        except KeyError as details:
            raise KeyError("Param %s required for cmdline is not present in %s"
                           % (details, self.str_long()))


class QCustomDevice(QBaseDevice):

    """
    Representation of the '-$option $param1=$value1,$param2...' qemu object.
    This representation handles only cmdline.
    """

    def __init__(self, dev_type, params=None, aobject=None,
                 parent_bus=None, child_bus=None, backend=None):
        """
        :param dev_type: The desired -$option parameter (device, chardev, ..)
        """
        super(QCustomDevice, self).__init__(dev_type, params, aobject,
                                            parent_bus, child_bus)
        if backend:
            self.__backend = backend
        else:
            self.__backend = None

    def cmdline(self):
        """ :return: cmdline command to define this device """
        if self.__backend and self.params.get(self.__backend):
            out = "-%s %s," % (self.type, self.params.get(self.__backend))
            params = self.params.copy()
            del params[self.__backend]
        else:
            out = "-%s " % self.type
            params = self.params
        for key, value in six.iteritems(params):
            if value != "NO_EQUAL_STRING":
                out += "%s=%s," % (key, value)
            else:
                out += "%s," % key
        if out[-1] == ',':
            out = out[:-1]
        return out

    def cmdline_nd(self):
        """
        Command line without dynamic parameters.

        :return: cmdline command to define this device without dynamic parameters.
        """
        if self.__backend and self.params.get(self.__backend):
            out = "-%s %s," % (self.type, self.params.get(self.__backend))
            params = self.params.copy()
            del params[self.__backend]
        else:
            out = "-%s " % self.type
            params = self.params
        for key, value in six.iteritems(params):
            if value != "NO_EQUAL_STRING":
                if key in self.dynamic_params:
                    out += "%s=DYN," % (key,)
                else:
                    out += "%s=%s," % (key, value)
            else:
                out += "%s," % key
        if out[-1] == ',':
            out = out[:-1]
        return out


class QDrive(QCustomDevice):

    """
    Representation of the '-drive' qemu object without hotplug support.
    """

    def __init__(self, aobject, use_device=True):
        child_bus = QDriveBus('drive_%s' % aobject, aobject)
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
            LOG.warn("Ignoring 'addr=%s' parameter of %s due of old qemu"
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
            if isinstance(bus, QDriveBus):
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
            if isinstance(bus, QDriveBus):
                for dev in bus:
                    self.__hook_drive_bus = dev.get_param('drive')
                    dev['drive'] = None
                break

    def unplug_unhook(self):
        """ Set back the previous 'drive' (unsafe, using the last value) """
        if self.__hook_drive_bus is not None:
            for bus in self.child_bus:
                if isinstance(bus, QDriveBus):
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
            if isinstance(bus, QDriveBus):
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
            if isinstance(bus, QDriveBus):
                for dev in bus:
                    self.__hook_drive_bus = dev.get_param('drive')
                    dev['drive'] = None
                break

    def unplug_unhook(self):
        """ Set back the previous 'drive' (unsafe, using the last value) """
        if self.__hook_drive_bus is not None:
            for bus in self.child_bus:
                if isinstance(bus, QDriveBus):
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


class QBlockdevNode(QCustomDevice):
    """ Representation of the '-blockdev' qemu object. """

    TYPE = None

    def __init__(self, aobject, child_bus=None, is_root=True):
        """
        :param aobject: Related autotest object(e.g, image1).
        :type aobject: str
        :param child_bus: List of buses, which this device provides.
        :type child_bus: qdevice.QDriveBus
        :param is_root: True if the blockdev node is root node, else False.
        :type is_root: bool
        """
        super(QBlockdevNode, self).__init__(
            "blockdev", {}, aobject, (), child_bus)

        self._child_nodes = []
        self._parent_node = None
        self._is_root = is_root
        self._set_root(is_root)
        self.set_param('driver', self.TYPE)

    def _set_root(self, flag):
        self._is_root = flag
        if self._is_root:
            self.params['node-name'] = '%s_%s' % ('drive', self.aobject)
        else:
            self.params['node-name'] = '%s_%s' % (self.TYPE, self.aobject)

    def get_child_nodes(self):
        """
        Get the child blockdev nodes.

        :return: list of child blockdev nodes.
        :rtype: list
        """
        return self._child_nodes

    def _set_parent_node(self, node):
        self._parent_node = node

    def get_parent_node(self):
        """ Get parent blockdev node. """
        return self._parent_node

    def add_child_node(self, node):
        """
        Add a child blockdev node.

        :param node: the blockdev node which will be added.
        :type node: qdevices.QBlockdevNode
        """
        node._set_root(False)
        self._child_nodes.append(node)
        node._set_parent_node(self)

    def del_child_node(self, node):
        """
        Delete a child blockdev node.

        :param node: the blockdev node which will be deleted.
        :type node: qdevices.QBlockdevNode
        """
        self._child_nodes.remove(node)
        node._set_parent_node(None)

    def clear_child_nodes(self):
        """ Delete all child blockdev nodes. """
        self._child_nodes.clear()

    @staticmethod
    def _convert_blkdev_args(args):
        """
        Convert string type of 'on' and 'off' to boolean, and create new dict
        (e.g: 'cache': {'direct': 'true'}) from key which include symbol '.'
        (e.g: 'cache.direct': 'true') to adhere to the blockdev qmp syntax.

        :param args: Dictionary with the qmp parameters.
        :type args: dict
        :return: Converted args.
        :rtype: dict
        """
        new_args = dict()
        for key, value in six.iteritems(args):
            if value in ('on', 'yes'):
                value = True
            elif value in ('off', 'no'):
                value = False

            parts = key.split(".")
            d = new_args
            for part in parts[:-1]:
                if part not in d:
                    d[part] = dict()
                d = d[part]
            d[parts[-1]] = value

        return new_args

    def hotplug_qmp(self):
        """
        Hot plug this blockdev node by qmp.

        :return: Hot plug qemu command and arguments.
        :rtype: tuple
        """
        return "blockdev-add", self._convert_blkdev_args(self.params)

    def unplug_qmp(self):
        """
        Unplug this blockdev node by qmp.

        :return: Unplug qemu command and arguments.
        :rtype: tuple
        """
        return "blockdev-del", {"node-name": self.get_qid()}

    def verify_hotplug(self, out, monitor):
        """
        Verify the status of hot plug.

        :param out: Output of the hot plug command.
        :type out: str
        :param monitor: Monitor used for unplugging.
        :type monitor: qemu_monitor.QMPMonitor
        :return: True when successful, False when unsuccessful.
        :rtype: bool
        """
        return len(out) == 0

    def verify_unplug(self, out, monitor):
        """
        Verify the status of unplugging.

        :param out: Output of the unplug command.
        :type out: str
        :param monitor: Monitor used for unplugging.
        :type monitor: qemu_monitor.QMPMonitor
        :return: True when successful, False when unsuccessful.
        :rtype: bool
        """
        return len(out) == 0

    def set_param(self, option, value, option_type=None):
        """
        Set device param using qemu notation ("on", "off" instead of bool...)
        It restricts setting of the 'node-name' param as it's automatically
        created.

        :param option: Which option's value to set.
        :type option: str
        :param value: New value.
        :type value: str
        :param option_type: Type of the option.
        :type option_type: bool
        """
        if option == 'node-name':
            raise KeyError(
                "Blockdev node-name is automatically created from aobject. %s"
                % self.aobject)
        super(QBlockdevNode, self).set_param(option, value, option_type)

    def get_qid(self):
        """ Get the node name instead of qemu id. """
        return self.params.get('node-name')


class QBlockdevFormatNode(QBlockdevNode):
    """ New a format type blockdev node. """

    def __init__(self, aobject):
        child_bus = QDriveBus('drive_%s' % aobject, aobject)
        super(QBlockdevFormatNode, self).__init__(aobject, child_bus)
        self.__hook_drive_bus = None

    def get_children(self):
        """ Device bus should be removed too. """
        for bus in self.child_bus:
            if isinstance(bus, QDriveBus):
                drive_bus = bus
                self.rm_child_bus(bus)
                break
        devices = super(QBlockdevFormatNode, self).get_children()
        self.add_child_bus(drive_bus)
        return devices

    def unplug_hook(self):
        """
        Devices from this bus are not removed, only 'drive' is set to None.
        """
        for bus in self.child_bus:
            if isinstance(bus, QDriveBus):
                for dev in bus:
                    self.__hook_drive_bus = dev.get_param('drive')
                    dev['drive'] = None
                break

    def unplug_unhook(self):
        """
        Set back the previous 'drive' (unsafe, using the last value).
        """
        if self.__hook_drive_bus is not None:
            for bus in self.child_bus:
                if isinstance(bus, QDriveBus):
                    for dev in bus:
                        dev['drive'] = self.__hook_drive_bus
                    break


class QBlockdevFormatQcow2(QBlockdevFormatNode):
    """ New a format qcow2 blockdev node. """
    TYPE = 'qcow2'


class QBlockdevFormatRaw(QBlockdevFormatNode):
    """ New a format raw blockdev node. """
    TYPE = 'raw'


class QBlockdevFormatLuks(QBlockdevFormatNode):
    """ New a format luks blockdev node. """
    TYPE = 'luks'


class QBlockdevProtocol(QBlockdevNode):
    """ New a protocol blockdev node. """

    def __init__(self, aobject):
        super(QBlockdevProtocol, self).__init__(aobject, None, False)


class QBlockdevProtocolFile(QBlockdevProtocol):
    """ New a protocol file blockdev node. """
    TYPE = 'file'


class QBlockdevProtocolNullCo(QBlockdevProtocol):
    """ New a protocol null-co node. """
    TYPE = 'null-co'


class QBlockdevProtocolHostDevice(QBlockdevProtocol):
    """ New a protocol host_device blockdev node. """
    TYPE = 'host_device'


class QBlockdevProtocolBlkdebug(QBlockdevProtocol):
    """ New a protocol blkdebug blockdev node. """
    TYPE = 'blkdebug'


class QBlockdevProtocolHostCdrom(QBlockdevProtocol):
    """ New a protocol host_cdrom blockdev node. """
    TYPE = 'host_cdrom'


class QBlockdevProtocolISCSI(QBlockdevProtocol):
    """ New a protocol iscsi blockdev node. """
    TYPE = 'iscsi'


class QBlockdevProtocolRBD(QBlockdevProtocol):
    """ New a protocol rbd blockdev node. """
    TYPE = 'rbd'


class QBlockdevFilter(QBlockdevNode):
    pass


class QBlockdevFilterCOR(QBlockdevFilter):
    TYPE = "copy-on-read"


class QBlockdevFilterThrottle(QBlockdevFilter):
    TYPE = "throttle"

    def __init__(self, aobject, group):
        super(QBlockdevFilterThrottle, self).__init__(aobject)
        self.parent_bus = ({"busid": group}, {"type": "ThrottleGroup"})
        self.set_param("throttle-group", group)


class QBlockdevProtocolGluster(QBlockdevProtocol):
    """ New a protocol gluster blockdev node. """
    TYPE = 'gluster'

    def hotplug_qmp(self):
        # TODO: design a new _convert_blkdev_args to handle list
        # of dicts, e.g. convert 'server.0.host', 'server.1.host'
        # to {'server': [{'host':xx}, {'host':xx}]}
        servers = {}
        args = OrderedDict()
        p = re.compile(r'server\.(?P<index>\d+)\.(?P<opt>.+)')

        for key, value in six.iteritems(self.params):
            m = p.match(key)
            if m is not None:
                index = int(m.group('index'))
                servers.setdefault(index, {})
                servers[index].update({m.group('opt'): value})
            else:
                args[key] = value

        params = self._convert_blkdev_args(args)
        params['server'] = [servers[i] for i in sorted(servers)]

        return "blockdev-add", params


class QBlockdevProtocolNBD(QBlockdevProtocol):
    """ New a protocol nbd blockdev node. """
    TYPE = 'nbd'


class QBlockdevProtocolNVMe(QBlockdevProtocol):
    """ New a protocol NVMe blockdev node. """
    TYPE = 'nvme'


class QBlockdevProtocolSSH(QBlockdevProtocol):
    """ New a protocol ssh blockdev node. """
    TYPE = 'ssh'


class QBlockdevProtocolHTTP(QBlockdevProtocol):
    """ New a protocol http blockdev node. """
    TYPE = 'http'


class QBlockdevProtocolHTTPS(QBlockdevProtocol):
    """ New a protocol https blockdev node. """
    TYPE = 'https'


class QBlockdevProtocolFTP(QBlockdevProtocol):
    """ New a protocol ftp blockdev node. """
    TYPE = 'ftp'


class QBlockdevProtocolFTPS(QBlockdevProtocol):
    """ New a protocol ftps blockdev node. """
    TYPE = 'ftps'


class QDevice(QCustomDevice):

    """
    Representation of the '-device' qemu object. It supports all methods.
    :note: Use driver format in full form - 'driver' = '...' (usb-ehci, ide-hd)
    """

    def __init__(self, driver=None, params=None, aobject=None,
                 parent_bus=None, child_bus=None):
        super(QDevice, self).__init__("device", params, aobject, parent_bus,
                                      child_bus, 'driver')
        if driver:
            self.set_param('driver', driver)
        self.hook_drive_bus = None

    def _get_alternative_name(self):
        """ :return: alternative object name """
        if self.params.get('driver'):
            return self.params.get('driver')

    def hotplug_hmp(self):
        """ :return: the hotplug monitor command """
        if self.params.get('driver'):
            params = self.params.copy()
            out = "device_add %s" % params.pop('driver')
            params = _convert_args(params)
            if params:
                out += ",%s" % params
        else:
            out = "device_add %s" % _convert_args(self.params)
        return out

    def hotplug_qmp(self):
        """ :return: the hotplug monitor command """
        return "device_add", self.params

    def hotplug_hmp_nd(self):
        """ :return: the hotplug monitor command without dynamic parameters"""
        if self.params.get('driver'):
            params = self.params.copy()
            out = "device_add %s" % params.pop('driver')
            for key in self.dynamic_params:
                params[key] = "DYN"
            params = _convert_args(params)
            if params:
                out += ",%s" % params
        else:
            params = self.params.copy()
            for key in self.dynamic_params:
                params[key] = "DYN"
            out = "device_add %s" % _convert_args(params)
        return out

    def hotplug_qmp_nd(self):
        """ :return: the hotplug monitor command without dynamic parameters"""
        params = self.params.copy()
        for key in self.dynamic_params:
            params[key] = "DYN"
        return "device_add", params

    def get_children(self):
        """ Device bus should be removed too """
        devices = super(QDevice, self).get_children()
        if self.hook_drive_bus:
            devices.append(self.hook_drive_bus)
        return devices

    def unplug_hmp(self):
        """ :return: the unplug monitor command """
        if self.get_qid():
            return "device_del %s" % self.get_qid()
        else:
            raise DeviceError("Device has no qemu_id.")

    def unplug_qmp(self):
        """ :return: the unplug monitor command """
        if self.get_qid():
            return "device_del", {'id': self.get_qid()}
        else:
            raise DeviceError("Device has no qemu_id.")

    def verify_unplug(self, out, monitor):
        out = monitor.info("qtree", debug=False)
        if "unknown command" in out:       # Old qemu don't have info qtree
            return out
        dev_id_name = 'id "%s"' % self.get_qid()
        if dev_id_name in out:
            return False
        else:
            return True

    # pylint: disable=E0202
    def verify_hotplug(self, out, monitor):
        out = monitor.info("qtree", debug=False)
        if "unknown command" in out:       # Old qemu don't have info qtree
            return out
        dev_id_name = 'id "%s"' % self.get_qid()
        if dev_id_name in out:
            return True
        else:
            return False


class QGlobal(QBaseDevice):

    """
    Representation of qemu global setting (-global driver.property=value)
    """

    def __init__(self, driver, prop, value, aobject=None,
                 parent_bus=None, child_bus=None):
        """
        :param driver: Which global driver to set
        :param prop: Which property to set
        :param value: What's the desired value
        :param params: component's parameters
        :param aobject: Autotest object which is associated with this device
        :param parent_bus: bus(es), in which this device is plugged in
        :param child_bus: bus, which this device provides
        """
        params = {'driver': driver, 'property': prop, 'value': value}
        super(QGlobal, self).__init__('global', params, aobject,
                                      parent_bus, child_bus)

    def cmdline(self):
        return "-global %s.%s=%s" % (self['driver'], self['property'],
                                     self['value'])


class QFloppy(QGlobal):

    """
    Imitation of qemu floppy disk defined by -global isa-fdc.drive?=$drive
    """

    def __init__(self, unit=None, drive=None, aobject=None, parent_bus=None,
                 child_bus=None):
        """
        :param unit: Floppy unit (None, 0, 1 or driveA, driveB)
        :param drive: id of drive
        :param aobject: Autotest object which is associated with this device
        :param parent_bus: bus(es), in which this device is plugged in
        :param child_bus: bus(es), which this device provides
        """
        super(QFloppy, self).__init__('isa-fdc', unit, drive, aobject,
                                      parent_bus, child_bus)

    def _get_alternative_name(self):
        return "floppy-%s" % (self.get_param('property'))

    def set_param(self, option, value, option_type=None):
        """
        drive and unit params have to be 'translated' as value and property.
        """
        if option == 'drive':
            option = 'value'
        elif option == 'unit':
            option = 'property'
        super(QFloppy, self).set_param(option, value, option_type)


class QObject(QCustomDevice):

    """
    Representation of the '-object backend' qemu object.
    """

    QMP_PROPS_VERSION_SCOPE = '(, 6.0.0)'

    def __init__(self, backend, params=None):
        kwargs = {'dev_type': 'object',
                  'params': params,
                  'backend': 'backend'}
        super(QObject, self).__init__(**kwargs)
        self.set_param('backend', backend)

    def get_children(self):
        """ Device bus should be removed too """
        devices = super(QObject, self).get_children()
        if getattr(self, 'hook_drive_bus', None):
            devices.append(self.hook_drive_bus)
        return devices

    def _get_alternative_name(self):
        """ :return: alternative object name """
        if self.get_param('backend'):
            return self.params.get('backend')

    def hotplug_hmp(self):
        """ :return: the hotplug monitor command """
        if self.params.get('backend'):
            params = self.params.copy()
            out = "object_add %s" % params.pop('backend')
            params = _convert_args(params)
            if params:
                out += ",%s" % params
        else:
            out = "object_add %s" % _convert_args(self.params)
        return out

    def _refresh_hotplug_props(self, params):
        """
        Refresh hotplug optional props as per params.

        :return: A dict containing hotplug optional props.
        """
        return params

    def _hotplug_qmp_mapping(self, qemu_version):
        return self.hotplug_qmp_lt_600 if qemu_version in VersionInterval(
            self.QMP_PROPS_VERSION_SCOPE) else self.hotplug_qmp

    def hotplug_qmp(self):
        """ :return: the object-add command (since 6.0.0)"""
        params = self.params.copy()

        # qom-type and id are mandatory
        kwargs = {
            "qom-type": params.pop("backend"),
            "id": params.pop("id")
        }

        # optional params
        params = self._refresh_hotplug_props(params)
        if len(params) > 0:
            kwargs.update(params)

        return "object-add", kwargs

    def hotplug_qmp_lt_600(self):
        """ :return: the object-add command (before 6.0.0)"""
        params = self.params.copy()

        # qom-type and id are mandatory
        kwargs = {
            "qom-type": params.pop("backend"),
            "id": params.pop("id")
        }

        # props is optional
        params = self._refresh_hotplug_props(params)
        if len(params) > 0:
            kwargs["props"] = params

        return "object-add", kwargs

    def hotplug_hmp_nd(self):
        """ :return: the hotplug monitor command without dynamic parameters"""
        if self.params.get('backend'):
            params = self.params.copy()
            out = "object_add %s" % params.pop('backend')
            for key in self.dynamic_params:
                params[key] = "DYN"
            params = _convert_args(params)
            if params:
                out += ",%s" % params
        else:
            params = self.params.copy()
            for key in self.dynamic_params:
                params[key] = "DYN"
            out = "object_add %s" % _convert_args(params)
        return out

    def hotplug_qmp_nd(self):
        """ :return: the hotplug monitor command without dynamic parameters"""
        params = self.params.copy()
        for key in self.dynamic_params:
            params[key] = "DYN"
        return "object-add", params

    def unplug_hmp(self):
        """ :return: the unplug monitor command """
        if self.get_qid():
            return "object_del %s" % self.get_qid()
        else:
            raise DeviceError("Device has no qemu_id.")

    def unplug_qmp(self):
        """ :return: the unplug monitor command """
        if self.get_qid():
            return "object-del", {'id': self.get_qid()}
        else:
            raise DeviceError("Device has no qemu_id.")

    def verify_unplug(self, out, monitor):
        return len(out) == 0

    # pylint: disable=E0202
    def verify_hotplug(self, out, monitor):
        return len(out) == 0


class QIOThread(QObject):
    """iothread object.
    attributes of iothread
    ["id", "poll-max-ns", "poll-grow", "poll-shrink"]
    """

    def __init__(self, iothread_id, params=None):
        if params is None:
            params = dict()
        params["id"] = iothread_id
        kwargs = dict(backend="iothread", params=params)
        super(QIOThread, self).__init__(**kwargs)
        self.set_aid(iothread_id)
        self.iothread_bus = QIOThreadBus(iothread_id)
        self.add_child_bus(self.iothread_bus)

    @staticmethod
    def _query(monitor):
        """Return a list of active iothreads."""
        out = monitor.info("iothreads", debug=False)
        if isinstance(monitor, qemu_monitor.HumanMonitor):
            pattern = (r"([\w-]+):\s+(thread_id)=(\d+)\s+(poll-max-ns)=(\d+)"
                       r"\s+(poll-grow)=(\d+)\s+(poll-shrink)=(\d+)")
            result = []
            for t in re.findall(pattern, out):
                it_dict = {}
                it_dict["id"] = t[0]
                it_dict.update(zip(t[1::2], t[2::2]))
                result.append(it_dict)
            out = result
        return out

    def get_children(self):
        """Get child devices, always empty."""
        # iothread could be removed without unplug child devices
        return []

    def unplug_hook(self):
        """Remove iothread from attached devices' params."""
        for device in self.iothread_bus:
            device.set_param("iothread", None)

    def unplug_unhook(self):
        """Reset attached devices' params."""
        for device in self.iothread_bus:
            device.set_param(self.get_qid())

    def _is_attached_to_qemu(self, monitor):
        """Check if iothread is in use by QEMU."""
        out = QIOThread._query(monitor)
        return any(self.get_qid() == iothread["id"] for iothread in out)

    def verify_hotplug(self, out, monitor):
        """Verify if it is plugged into VM."""
        return self._is_attached_to_qemu(monitor)

    def verify_unplug(self, out, monitor):
        """Verify if it is unplugged from VM."""
        return not self._is_attached_to_qemu(monitor)


class QThrottleGroup(QObject):
    """
    throttle-group object.
    """

    def __init__(self, group_id, props):
        self._raw_limits = props.copy()

        params = QThrottleGroup._map_key(self.raw_limits)
        params["id"] = group_id
        kwargs = dict(backend="throttle-group", params=params)
        super(QThrottleGroup, self).__init__(**kwargs)
        self.throttle_group_bus = QThrottleGroupBus(group_id)
        self.add_child_bus(self.throttle_group_bus)
        self.set_aid(group_id)
        self.hook_drive_bus = None

    @staticmethod
    def _map_key(params):
        # FIXME: temporary solution to simplify conversion. There are some
        #  experimental options for throttle-group object (with x- prefix).
        #  It should be updated once final options are confirmed.
        return {'x-%s' % k: v for k, v in params.items()}

    @property
    def raw_limits(self):
        """Return raw throttle group properties."""
        return self._raw_limits

    @raw_limits.setter
    def raw_limits(self, props):
        """Update raw throttle group properties."""
        self._raw_limits.update(props)

    def _refresh_hotplug_props(self, params):
        params["limits"] = self.raw_limits
        return params

    def _query(self, monitor):
        """Check if throttle is in use by QEMU."""
        try:
            monitor.qom_get(self.params["id"], "limits")
            return True
        except qemu_monitor.MonitorError as err:
            if "DeviceNotFound" in str(err):
                LOG.warning(err)
                return False
            raise err

    def verify_hotplug(self, out, monitor):
        """Verify if it is plugged into VM."""
        return self._query(monitor)

    def verify_unplug(self, out, monitor):
        """Verify if it is unplugged from VM."""
        return not self._query(monitor)


class Memory(QObject):

    """
    QOM memory object, support for pinning memory on host NUMA nodes.
    """

    def __init__(self, backend, params=None):
        qemu_binary = utils_misc.get_qemu_binary(params)
        self.attrs = utils_qemu.get_dev_attrs(qemu_binary, 'object', backend)
        params = params.copy_from_keys(self.attrs)
        super(Memory, self).__init__(backend, params)
        self.hook_drive_bus = None

    def _refresh_hotplug_props(self, params):
        convert_size = utils_misc.normalize_data_size
        args = (params["size"], "B", 1024)
        params["size"] = int(float(convert_size(*args)))
        if params.get("prealloc-threads"):
            params["prealloc-threads"] = int(params["prealloc-threads"])
        if params.get("host-nodes"):
            host_nodes = list(map(int, params["host-nodes"].split()))
            params["host-nodes"] = host_nodes
        for k in params:
            params[k] = True if params[k] == "yes" else params[k]
            params[k] = False if params[k] == "no" else params[k]
        return params

    def verify_unplug(self, out, monitor):
        """
        :param out: Output of the unplug command
        :param monitor: Monitor used for unplug
        :return: True when successful, False when unsuccessful
        """
        out = monitor.info("memdev", debug=False)
        memdev = self.get_qid()
        for dev in out:
            if dev["id"] == memdev:
                return False
        return True

    def verify_hotplug(self, out, monitor):
        """
        :param out: Output of the hotplug command
        :param monitor: Monitor used for hotplug
        :return: True when successful, False when unsuccessful
        """
        out = monitor.info("memdev", debug=False)
        memdev = self.get_qid()
        params = self.params.copy()
        for dev in out:
            if dev["id"] == memdev:
                if not params.get("host-nodes") and len(dev["host-nodes"]):
                    return False
                if params.get("host-nodes"):
                    host_nodes = list(map(int, params["host-nodes"].split()))
                    if dev["host-nodes"].sort() != host_nodes.sort():
                        return False
                args = (params["size"], "B", 1024)
                size = int(float(utils_misc.normalize_data_size(*args)))
                if dev["size"] != size:
                    return False
                dev.pop("size")
                dev.pop("host-nodes")
                for k in dev:
                    if params.get(k):
                        params[k] = True if params[k] == "yes" else params[k]
                        params[k] = False if params[k] == "no" else params[k]
                        if dev[k] != params[k]:
                            return False
                return True
        return False


class Dimm(QDevice):
    """
    PC-Dimm or NVDIMM device, support for memory hotplug using the device and
    QOM objects.
    """

    def __init__(self, params=None, dimm_type='pc-dimm'):
        qemu_binary = utils_misc.get_qemu_binary(params)
        self.attrs = utils_qemu.get_dev_attrs(qemu_binary, 'device', dimm_type)
        params = params.copy_from_keys(self.attrs)
        kwargs = {'driver': dimm_type,
                  'params': params}
        super(Dimm, self).__init__(**kwargs)
        self.set_param('driver', dimm_type)
        self.hook_drive_bus = None

    def verify_hotplug(self, out, monitor):
        out = monitor.info("memory-devices", debug=False)
        if "unknown command" in out:       # Old qemu don't have info qtree
            return out
        dev_id_name = self.get_qid()
        for item in out:
            if item['data']['id'] == dev_id_name:
                return True
        return False

    def verify_unplug(self, dev_type, monitor):
        out = monitor.info("memory-devices", debug=False)
        if "unknown command" in out:       # Old qemu don't have info qtree
            return out
        dev_id_name = self.get_qid()
        for item in out:
            if item['data']['id'] == dev_id_name:
                return False
        return True


class CharDevice(QCustomDevice):
    """
    Qemu Char Device object, hotplug and hotunplug only support via QMP
    monitor.
    """
    backends = [
        "null", "socket", "udp", "msmouse", "vc", "ringbuf", "file",
        "pipe", "pty", "stdio", "serial", "tty", "parallel", "parport",
        "spicevmc", "spiceport"
    ]

    def __init__(self,
                 params=None,
                 aobject=None,
                 parent_bus=None,
                 child_bus=None):
        backend = params.get("backend", "socket")
        self.verify_supported_backend(backend)
        options = self.get_supported_options(backend)
        params = params.copy_from_keys(options)
        params = self.format_params(params)
        params['backend'] = backend
        super(CharDevice, self).__init__(
            'chardev',
            backend='backend',
            params=params,
            aobject=aobject,
            parent_bus=parent_bus,
            child_bus=child_bus)

    def verify_supported_backend(self, backend):
        if backend not in self.backends:
            raise DeviceError("Unknow chardev backend '%s'" % backend)

    def get_supported_options(self, backend):
        """
        Get chardev backend support options.

        :param backend: chardev backend type which include in backends list.
        :return set: set of support options.
        """
        special_opts, common_opts = [], ["id", "logfile", "logappend"]

        if backend not in ["socket", "vc", "ringbuf",
                           "spiceport", "spicevmc"]:
            common_opts.append("mux")

        if backend in ["file", "pipe", "serial",
                       "tty", "parallel", "parport"]:
            special_opts.append("path")

        elif backend in ["spicevmc", "spiceport"]:
            special_opts += ["name", "debug"]

        elif backend in ["stdio"]:
            special_opts.append("signal")

        elif backend in ["socket"]:
            common_opts += ["server", "wait", "reconnect"]
            special_opts = ["host", "port", "to", "ipv4",
                            "ipv6", "nodelay", "path",
                            "abstract", "tight"]

        elif backend == 'udp':
            special_opts = ["host", "port", "localaddr",
                            "localport", "ipv4", "ipv6"]

        elif backend == 'ringbuf':
            special_opts = ["ringbuf_write_size"]

        return set(common_opts + special_opts)

    def format_params(self, params):
        """
        Format params by support options type

        :param params: chardev test params.
        :return dict: formatted params only include support options.
        """
        for opt in ["server", "telnet", "wait",
                    "ipv4", "ipv6", "nodelay", "mux", "signal"]:
            if params.get(opt) in ["yes", "on"]:
                params[opt] = "on"
            elif params.get(opt) in ["no", "off"]:
                params[opt] = 'off'
            elif opt in params:
                del params[opt]

        return params

    def get_qmp_args(self):
        """
        Get chardev hotplug required args by backend type

        :return dict: dict include chardev-add required args.
        """
        args = {"id": self.get_qid(),
                "backend": {"type": self.params.get("backend"),
                            "data": {}}}
        if self.params.get("backend") == "socket":
            if self.get_param("port"):
                addr_type = "inet"
                host = self.get_param("host") or "0.0.0.0"
                addr_data = {"host": host, "port": self.get_param("port")}
            else:
                addr_type = "unix"
                addr_data = {"path": self.get_param("path")}
            args["backend"]["data"]["addr"] = {"type": addr_type,
                                               "data": addr_data}
            if addr_type == "inet":
                sock_params = ["telnet", "ipv4", "ipv6", "nodelay"]
            else:
                sock_params = ["server", "wait"]

            for param in sock_params:
                if self.get_param(param) is None:
                    continue
                value = True if self.get_param(param) == 'on' else False
                args["backend"]["data"][param] = value
            return args

        if self.params.get("backend") == "file":
            args["backend"]["data"] = {"out": self.get_param("path")}
            return args

        if self.params.get("backend") in ["null", "pty"]:
            return args

        if self.params.get("backend") in ["serial", "parallel"]:
            args["backend"]["data"] = {"device": self.get_param("path")}
            return args

        if self.params.get("backend") in "ringbuf":
            args["backend"]["data"] = {
                "size": self.get_param("ringbuf_write_size")}
            return args

        raise DeviceError("chardev '%s' not support hotplug" %
                          self.params.get("backend"))

    def hotplug_qmp(self):
        """ :return: hotplug command and args"""
        return "chardev-add", self.get_qmp_args()

    def hotplug_hmp(self):
        """ :return: the hotplug monitor command """
        raise NotImplementedError

    def unplug_hmp(self):
        """ :return: the unplug monitor command """
        raise NotImplementedError

    def unplug_qmp(self):
        """ :return: unplug command and args"""
        return "chardev-remove", {"id": self.get_qid()}

    def verify_hotplug(self, out, monitor):
        """
        :param out: Output of the hotplug command
        :param monitor: Monitor used for hotplug
        :return: True when successful, False when unsuccessful, string/None
                 when can't decide.
        """
        out = monitor.query("chardev")
        return "\'%s\'" % self.get_qid() in str(out)

    def verify_unplug(self, out, monitor):  # pylint: disable=W0613,R0201
        """
        :param out: Output of the unplug command
        :param monitor: Monitor used for unplug
        """
        out = monitor.query("chardev")
        return "\'%s\'" % self.get_qid() not in str(out)


class QCPUDevice(QDevice):
    """
    CPU Device object, supports hot plug/unplug vcpu device with specified
    properties.
    """

    def __init__(self, cpu_driver, enable, params=None, aobject=None,
                 parent_bus=None):
        """
        :param cpu_driver: cpu driver name
        :type cpu_driver: str
        :param enable: Whether to enable this cpu device in qemu
        :type enable: bool
        """
        super(QCPUDevice, self).__init__(cpu_driver, params, aobject,
                                         parent_bus)
        self._enabled = enable

    def is_enabled(self):
        """Return True if cpu device is enabled"""
        return self._enabled

    def cmdline(self):
        """
        :return: cmdline command to define this device. (if enabled)
        """
        if self._enabled:
            return super(QCPUDevice, self).cmdline()
        return ""

    def cmdline_nd(self):
        """
        :return: cmdline command to define this device without dynamic
                 parameters. (if enabled)
        """
        if self._enabled:
            return super(QCPUDevice, self).cmdline_nd()
        return ""

    def enable(self, monitor):
        """Alias for hotplug"""
        # False positive issue caused E1121, disable it
        out = self.hotplug(monitor, None)  # pylint: disable=E1121
        ver_out = not bool(out)
        if ver_out:
            self._enabled = True
        return out, ver_out

    def disable(self, monitor):
        """Alias for unplug"""
        out = self.unplug(monitor)
        ver_out = not bool(out)
        if ver_out:
            self._enabled = False
        return out, ver_out


class QDaemonDev(QBaseDevice):
    """
    Virtual daemon device.
    """

    def __init__(self, name, aobject, child_bus=None):
        """
        :param name: The daemon name.
        :type name: str
        :param aobject: The aobject of daemon.
        :type aobject: str
        :param child_bus: List of buses, which this device provides.
        :type child_bus: QSparseBus
        """
        aid = '%s_%s' % (name, aobject)
        super(QDaemonDev, self).__init__(name, aobject=aobject, child_bus=child_bus)
        self.set_aid(aid)
        self.set_param('name', name)
        self._daemon_process = None

    def is_daemon_alive(self):
        """Check whether daemon is alive."""
        return bool(self._daemon_process and self._daemon_process.is_alive())

    def start_daemon(self):
        """Start daemon."""
        cmd = self.get_param('cmd')
        name = self.get_param('name')
        run_bg_kwargs = self.get_param('run_bg_kwargs', {})
        status_active = self.get_param('status_active')
        read_until_timeout = self.get_param('read_until_timeout', 5)
        start_until_timeout = self.get_param('start_until_timeout', 1)

        if cmd is None:
            LOG.warn('No provided command to start %s daemon.', name)
            self._daemon_process = None

        if self.is_daemon_alive():
            return

        LOG.info('Running %s daemon command %s.', name, cmd)
        self._daemon_process = aexpect.run_bg(cmd, **run_bg_kwargs)
        if status_active:
            self._daemon_process.read_until_any_line_matches(
                status_active, timeout=read_until_timeout)
        else:
            time.sleep(start_until_timeout)
        LOG.info("Created %s daemon process with parent PID %d.",
                 name, self._daemon_process.get_pid())

    def stop_daemon(self):
        """Stop daemon."""
        if self._daemon_process is not None:
            try:
                if not utils_misc.wait_for(lambda: not self.is_daemon_alive(),
                                           self.get_param('stop_timeout', 3)):
                    raise DeviceError('The %s daemon is still alive.' %
                                      self.get_param('name'))
            finally:
                self._daemon_process.close()
                self._daemon_process = None

    def clear(self):
        """Clear daemon."""
        try:
            self.stop_daemon()
        except DeviceError:
            pass

    def hotplug(self, monitor, qemu_version):
        """Hot plug daemon."""
        self.start_daemon()

    def verify_hotplug(self, out, monitor):
        """Verify daemon after hotplug."""
        return self.is_daemon_alive()

    def unplug(self, monitor):
        """Unplug daemon."""
        self.stop_daemon()

    def verify_unplug(self, out, monitor):
        """Verify the status of daemon."""
        return not self.is_daemon_alive()

    def get_qid(self):
        """Get qid."""
        return self.get_aid()

    def cmdline(self):
        """Start daemon command line."""
        self.start_daemon()
        return ''

    def __eq__(self, other):
        return isinstance(other, self.__class__)

    def __ne__(self, other):
        return not self.__eq__(other)

    __hash__ = None


class QVirtioFSDev(QDaemonDev):
    """
    Virtiofs pseudo device.
    """

    def __init__(self, aobject, binary, sock_path, source, extra_options=None,
                 enable_debug_mode=False):
        """
        :param aobject: The aobject of virtiofs daemon.
        :type aobject: str
        :param binary: The binary of virtiofs daemon.
        :type binary: str
        :param sock_path: The socket path of of virtiofs daemon.
        :type sock_path: str
        :param source: The source of virtiofs daemon.
        :type source: str
        :param extra_options: The external options of virtiofs daemon.
        :type extra_options: str
        :param enable_debug_mode: Enable debug mode of virtiofs daemon.
        :type enable_debug_mode: bool
        """
        super(QVirtioFSDev, self).__init__('virtiofs', aobject=aobject,
                                           child_bus=QUnixSocketBus(sock_path, aobject))
        self.set_param('binary', binary)
        self.set_param('sock_path', sock_path)
        self.set_param('source', source)
        self.set_param('extra_options', extra_options)
        self.set_param('enable_debug_mode', enable_debug_mode)

    def _handle_log(self, line):
        """Handle the log of virtiofs daemon."""
        name = self.get_param('name')
        try:
            utils_misc.log_line('%s-%s.log' % (self.get_qid(), name), line)
        except Exception as e:
            LOG.warn("Can't log %s-%s, output: '%s'.", self.get_qid(), name, e)

    def start_daemon(self):
        """Start the virtiofs daemon in background."""
        fsd_cmd = '%s --socket-path=%s' % (self.get_param('binary'),
                                           self.get_param('sock_path'))
        fsd_cmd += ' -o source=%s' % self.get_param('source')
        if self.get_param('enable_debug_mode') == "on":
            fsd_cmd += ' -d'
            self.set_param('status_active',
                           'Waiting for vhost-user socket connection')

        if self.get_param('extra_options'):
            fsd_cmd += self.get_param('extra_options')

        self.set_param('cmd', fsd_cmd)
        self.set_param('run_bg_kwargs', {'output_func': self._handle_log,
                                         'auto_close': False})
        super(QVirtioFSDev, self).start_daemon()

    def __eq__(self, other):
        if super(QVirtioFSDev, self).__eq__(other):
            return self.get_param('sock_path') == other.get_param('sock_path')
        return False


class QSwtpmDev(QDaemonDev):
    """
    Virtual swtpm pseudo device.
    """

    def __init__(self, aobject, binary, sock_path, storage_path,
                 version=None, extra_options=None):
        """
        :param aobject: The auto object of swtpm daemon.
        :type aobject: str
        :param binary: The binary of swtpm daemon.
        :type binary: str
        :param sock_path: The socket path of of swtpm daemon.
        :type sock_path: str
        :param storage_path: The path to the directory for tpm state
        :type storage_path: str
        :param version: the version of tpm functionality.
        :type version: str
        :type storage_path: str
        :param extra_options: The external options of swtpm daemon.
        :type extra_options: str
        """
        super(QSwtpmDev, self).__init__('vtpm', aobject=aobject,
                                        child_bus=QUnixSocketBus(sock_path, aobject))
        self.set_param('binary', binary)
        self.set_param('sock_path', sock_path)
        self.set_param('storage_path', storage_path)
        self.set_param('version', version)
        self.set_param('extra_options', extra_options)

    def start_daemon(self):
        tpm_cmd = '%s socket' % self.get_param('binary')
        tpm_cmd += ' --ctrl type=unixio,path=%s,mode=0600' % self.get_param('sock_path')
        tpm_cmd += ' --tpmstate dir=%s,mode=0600' % self.get_param('storage_path')
        tpm_cmd += ' --terminate'

        if self.get_param('version') in ('2.0', ):
            tpm_cmd += ' --tpm2'

        log_dir = utils_misc.get_log_file_dir()
        tpm_cmd += ' --log file=%s' % os.path.join(log_dir, '%s_swtpm.log' % self.get_qid())

        if self.get_param('extra_options'):
            tpm_cmd += self.get_param('extra_options')

        self.set_param('cmd', tpm_cmd)
        self.set_param('run_bg_kwargs', {'auto_close': False})
        super(QSwtpmDev, self).start_daemon()

    def __eq__(self, other):
        if super(QSwtpmDev, self).__eq__(other):
            return self.get_param('sock_path') == other.get_param('sock_path')
        return False


#
# Bus representations
# HDA, I2C, IDE, ISA, PCI, SCSI, System, uhci, ehci, ohci, xhci, ccid,
# virtio-serial-bus
#
class QSparseBus(object):

    """
    Universal bus representation object.

    It creates an abstraction of the way how buses works in qemu. Additionally
    it can store incorrect records (out-of-range addr, multiple devs, ...).
    Everything with bad* prefix means it concerns the bad records (badbus).

    You can insert and remove device to certain address, address ranges or let
    the bus assign first free address. The order of addr_spec does matter since
    the last item is incremented first.

    There are 3 different address representation used:

    stor_addr
        stored address representation '$first-$second-...-$ZZZ'
    addr
        internal address representation [$first, $second, ..., $ZZZ]
    device_addr
        qemu address stored into separate device params (bus, port)
        device{$param1:$first, $param2:$second, ..., $paramZZZ, $ZZZ}

    :note: When you insert a device, it's properties might be updated (addr,..)
    """

    def __init__(self, bus_item, addr_spec, busid, bus_type=None, aobject=None,
                 atype=None):
        """
        :param bus_item: Name of the parameter which specifies bus (bus)
        :type bus_item: str
        :param addr_spec: Bus address specification [names][lengths]
        :type addr_spec: builtin.list
        :param busid: id of the bus (pci.0)
        :type busid: str
        :param bus_type: type of the bus (pci)
        :type bus_type: dict
        :param aobject: Related autotest object (image1)
        :type aobject: str
        :param atype: Autotest bus type
        :type atype: str
        """
        self.busid = busid
        self.type = bus_type
        self.aobject = aobject
        self.bus = {}                       # Normal bus records
        self.bus_item = bus_item            # bus param name
        self.addr_items = addr_spec[0]      # [names][lengths]
        self.addr_lengths = addr_spec[1]
        self.atype = atype
        self.__device = None
        self.first_port = [0] * len(addr_spec[0])

    def __str__(self):
        """ default string representation """
        return self.str_short()

    def __getitem__(self, item):
        """
        :param item: autotest id or QObject-like object
        :return: First matching object from this bus
        :raise KeyError: In case no match was found
        """
        if isinstance(item, QBaseDevice):
            if item in six.itervalues(self.bus):
                return item
        else:
            for device in six.itervalues(self.bus):
                if device.get_aid() == item:
                    return device
        raise KeyError("Device %s is not in %s" % (item, self))

    def get(self, item):
        """
        :param item: autotest id or QObject-like object
        :return: First matching object from this bus or None
        """
        if item in self:
            return self[item]

    def __delitem__(self, item):
        """
        Remove device from bus
        :param item: autotest id or QObject-like object
        :raise KeyError: In case no match was found
        """
        self.remove(self[item])

    def __len__(self):
        """ :return: Number of devices in this bus """
        return len(self.bus)

    def __contains__(self, item):
        """
        Is specified item in this bus?
        :param item: autotest id or QObject-like object
        :return: True - yes, False - no
        """
        if isinstance(item, QBaseDevice):
            if item in six.itervalues(self.bus):
                return True
        else:
            for device in self:
                if device.get_aid() == item:
                    return True
        return False

    def __iter__(self):
        """ Iterate over all defined devices. """
        return six.itervalues(self.bus)

    def str_short(self):
        """ short string representation """
        if self.atype:
            bus_type = self.atype
        else:
            bus_type = self.type
        return "%s(%s): %s" % (self.busid, bus_type, self._str_devices())

    def _str_devices(self):
        """ short string representation of the good bus """
        out = '{'
        for addr in sorted(self.bus.keys()):
            out += "%s:%s," % (addr, self.bus[addr])
        if out[-1] == ',':
            out = out[:-1]
        return out + '}'

    def str_long(self):
        """ long string representation """
        if self.atype:
            bus_type = self.atype
        else:
            bus_type = self.type
        return "Bus %s, type=%s\nSlots:\n%s" % (self.busid, bus_type,
                                                self._str_devices_long())

    def _str_devices_long(self):
        """ long string representation of devices in the good bus """
        out = ""
        for addr, dev in six.iteritems(self.bus):
            out += '%s< %4s >%s\n  ' % ('-' * 15, addr,
                                        '-' * 15)
            if isinstance(dev, six.string_types):
                out += '"%s"\n  ' % dev
            else:
                out += dev.str_long().replace('\n', '\n  ')
                out = out[:-3]
            out += '\n'
        return out

    def _increment_addr(self, addr, last_addr=None):
        """
        Increment addr base of addr_pattern and last used addr
        :param addr: addr_pattern
        :param last_addr: previous address
        :return: last_addr + 1
        """
        if not last_addr:
            last_addr = [0] * len(self.addr_lengths)
        i = -1
        while True:
            if i < -len(self.addr_lengths):
                return False
            if addr[i] is not None:
                i -= 1
                continue
            last_addr[i] += 1
            if last_addr[i] < self.addr_lengths[i]:
                return last_addr
            last_addr[i] = 0
            i -= 1

    @staticmethod
    def _addr2stor(addr):
        """
        Converts internal addr to storable/hashable address
        :param addr: internal address [addr1, addr2, ...]
        :return: storable address "addr1-addr2-..."
        """
        out = ""
        for value in addr:
            if value is None:
                out += '*-'
            else:
                out += '%s-' % value
        if out:
            return out[:-1]
        else:
            return "*"

    def _dev2addr(self, device):
        """
        Parse the internal address out of the device
        :param device: QBaseDevice device
        :return: internal address  [addr1, addr2, ...]
        """
        addr = []
        for key in self.addr_items:
            addr.append(none_or_int(device.get_param(key)))
        return addr

    def _set_first_addr(self, addr_pattern):
        """
        :param addr_pattern: Address pattern (full qualified or with None)
        :return: first valid address based on addr_pattern
        """
        use_reserved = True
        if addr_pattern is None:
            addr_pattern = [None] * len(self.addr_lengths)
        # set first usable addr
        last_addr = addr_pattern[:]
        if None in last_addr:  # Address is not fully specified
            use_reserved = False    # Use only free address
            for i in xrange(len(last_addr)):
                if last_addr[i] is None:
                    last_addr[i] = self.first_port[i]
        return last_addr, use_reserved

    def get_free_slot(self, addr_pattern):
        """
        Finds unoccupied address

        :param addr_pattern: Address pattern (full qualified or with None)
        :return: First free address when found, (free or reserved for this dev)
                 None when no free address is found, (all occupied)
                 False in case of incorrect address (oor)
        """
        # init
        last_addr, use_reserved = self._set_first_addr(addr_pattern)
        # Check the addr_pattern ranges
        for i in xrange(len(self.addr_lengths)):
            if (last_addr[i] < self.first_port[i] or
                    last_addr[i] >= self.addr_lengths[i]):
                return False
        # Increment addr until free match is found
        while last_addr is not False:
            if self._addr2stor(last_addr) not in self.bus:
                return last_addr
            if (use_reserved and
                    self.bus[self._addr2stor(last_addr)] == "reserved"):
                return last_addr
            last_addr = self._increment_addr(addr_pattern, last_addr)
        return None     # No free matching address found

    def _check_bus(self, device):
        """
        Check, whether this device can be plugged into this bus.
        :param device: QBaseDevice device
        :return: True in case ids are correct, False when not
        """
        if (device.get_param(self.bus_item) and
                device.get_param(self.bus_item) != self.busid):
            return False
        else:
            return True

    def _set_device_props(self, device, addr):
        """
        Set the full device address
        :param device: QBaseDevice device
        :param addr: internal address  [addr1, addr2, ...]
        """
        if self.bus_item:
            device.set_param(self.bus_item, self.busid)
        for i in xrange(len(self.addr_items)):
            device.set_param(self.addr_items[i], addr[i])

    def _update_device_props(self, device, addr):
        """
        Update values of previously set address items.
        :param device: QBaseDevice device
        :param addr: internal address  [addr1, addr2, ...]
        """
        if device.get_param(self.bus_item) is not None:
            device.set_param(self.bus_item, self.busid)
        for i in xrange(len(self.addr_items)):
            if device.get_param(self.addr_items[i]) is not None:
                device.set_param(self.addr_items[i], addr[i])

    def reserve(self, addr):
        """
        Reserve the slot
        :param addr: Desired address
        :type addr: internal [addr1, addr2, ..] or stor format "addr1-addr2-.."
        """
        if not isinstance(addr, six.string_types):
            addr = self._addr2stor(addr)
        self.bus[addr] = "reserved"

    def insert(self, device, strict_mode=False):
        """
        Insert device into this bus representation.

        :param device: QBaseDevice device
        :param strict_mode: Use strict mode (set optional params)
        :return: list of added devices on success,
                 string indicating the failure on failure.
        """
        additional_devices = []
        if not self._check_bus(device):
            return "BusId"
        try:
            addr_pattern = self._dev2addr(device)
        except (ValueError, LookupError):
            return "BasicAddress"
        addr = self.get_free_slot(addr_pattern)
        if addr is None:
            if None in addr_pattern:
                return "NoFreeSlot"
            else:
                return "UsedSlot"
        elif addr is False:
            return "BadAddr(%s)" % addr
        else:
            additional_devices.extend(self._insert(device,
                                                   self._addr2stor(addr)))
        if strict_mode:     # Set full address in strict_mode
            self._set_device_props(device, addr)
        else:
            self._update_device_props(device, addr)
        return additional_devices

    def _insert(self, device, addr):
        """
        Insert device into good bus
        :param device: QBaseDevice device
        :param addr: internal address  [addr1, addr2, ...]
        :return: List of additional devices
        """
        self.bus[addr] = device
        return []

    def prepare_hotplug(self, device):
        """
        Prepares a device to be hot-plugged into this bus;
        You need to call "insert" afterwards. Concurrent calls
        of "prepare_hotplug" and "insert" are not supported
        :param device: QDevice object
        """
        device.set_param("bus", self.busid)

    def remove(self, device):
        """
        Remove device from this bus
        :param device: QBaseDevice device
        :return: True when removed, False when the device wasn't found
        """
        if device in six.itervalues(self.bus):
            remove = None
            for key, item in six.iteritems(self.bus):
                if item is device:
                    remove = key
                    break
            if remove is not None:
                del(self.bus[remove])
                return True
        return False

    def set_device(self, device):
        """ Set the device in which this bus belongs """
        self.__device = device

    def get_device(self):
        """ Get device in which this bus is present """
        return self.__device

    def match_bus(self, bus_spec, type_test=True):
        """
        Check if the bus matches the bus_specification.
        :param bus_spec: Bus specification
        :type bus_spec: dict
        :param type_test: Match only type
        :type type_test: bool
        :return: True when the bus matches the specification
        :rtype: bool
        """
        if type_test and bus_spec.get('type'):
            if isinstance(bus_spec['type'], (tuple, list)):
                for bus_type in bus_spec['type']:
                    if bus_type == self.type:
                        return True
                return False
            elif self.type == bus_spec['type']:
                return True
        for key, value in six.iteritems(bus_spec):
            if isinstance(value, (tuple, list)):
                for val in value:
                    if self.__dict__.get(key, None) == val:
                        break
                else:
                    return False
            elif self.__dict__.get(key, None) != value:
                return False
        return True


class QStrictCustomBus(QSparseBus):

    """
    Similar to QSparseBus. The address starts with 1 and addr is always set
    """

    def __init__(self, bus_item, addr_spec, busid, bus_type=None, aobject=None,
                 atype=None, first_port=None):
        super(QStrictCustomBus, self).__init__(bus_item, addr_spec, busid,
                                               bus_type, aobject, atype)
        if first_port:
            self.first_port = first_port

    def _update_device_props(self, device, addr):
        """ in case this is usb-hub update the child port_prefix """
        self._set_device_props(device, addr)


class QNoAddrCustomBus(QSparseBus):

    """
    This is the opposite of QStrictCustomBus. Even when addr is set it's not
    updated in the device's params.
    """

    def _set_device_props(self, device, addr):
        pass

    def _update_device_props(self, device, addr):
        pass


class QUSBBus(QSparseBus):

    """
    USB bus representation including usb-hub handling.
    """

    def __init__(self, length, busid, bus_type, aobject=None,
                 port_prefix=""):
        """
        Bus type have to be generalized and parsed from original bus type:
        (usb-ehci == ehci, ich9-usb-uhci1 == uhci, ...)
        """
        # There are various usb devices for the same bus type, use only portion
        for bus in ('uhci', 'ehci', 'ohci', 'xhci'):
            if bus in bus_type:
                bus_type = bus
                break
        # Usb ports are counted from 1 so the length have to be +1
        super(QUSBBus, self).__init__('bus', [['port'], [length + 1]], busid,
                                      bus_type, aobject)
        self.__port_prefix = port_prefix
        self.__length = length
        self.first_port = [1]

    def _check_bus(self, device):
        """ Check port prefix in order to match addresses in usb-hubs """
        if not super(QUSBBus, self)._check_bus(device):
            return False
        port = device.get_param('port')   # 2.1.6
        if port or port == 0:   # If port is specified
            idx = str(port).rfind('.')
            if idx != -1:   # Strip last number and compare with port_prefix
                return port[:idx] == self.__port_prefix
            # Port is number, match only root usb bus
            elif self.__port_prefix != "":
                return False
        return True

    def _dev2addr(self, device):
        """
        Parse the internal address out of the device
        :param device: QBaseDevice device
        :return: internal address  [addr1, addr2, ...]
        """
        value = device.get_param('port')
        if value is None:
            addr = [None]
        # this part allows to specify the port of usb devices on the root bus
        elif not self.__port_prefix:
            addr = [int(value)]
        else:
            addr = [int(value[len(self.__port_prefix) + 1:])]
        return addr

    def __hook_child_bus(self, device, addr):
        """ If this is usb-hub, add child bus """
        # only usb hub needs customization
        if device.get_param('driver') != 'usb-hub':
            return
        _bus = [_ for _ in device.child_bus if not isinstance(_, QUSBBus)]
        _bus.append(QUSBBus(8, self.busid, self.type, device.get_aid(),
                            str(addr[0])))
        device.child_bus = _bus

    def _set_device_props(self, device, addr):
        """ in case this is usb-hub update the child port_prefix """
        if addr[0] or addr[0] == 0:
            if self.__port_prefix:
                addr = ['%s.%s' % (self.__port_prefix, addr[0])]
        self.__hook_child_bus(device, addr)
        super(QUSBBus, self)._set_device_props(device, addr)

    def _update_device_props(self, device, addr):
        """ in case this is usb-hub update the child port_prefix """
        self._set_device_props(device, addr)


class QDriveBus(QSparseBus):

    """
    QDrive bus representation (single slot, drive=...)
    """

    def __init__(self, busid, aobject=None):
        """
        :param busid: id of the bus (pci.0)
        :param aobject: Related autotest object (image1)
        """
        super(QDriveBus, self).__init__('drive', [[], []], busid, 'QDrive',
                                        aobject)

    def get_free_slot(self, addr_pattern):
        """ Use only drive as slot """
        if 'drive' in self.bus:
            return None
        else:
            return True

    @staticmethod
    def _addr2stor(addr):
        """ address is always drive """
        return 'drive'

    def _update_device_props(self, device, addr):
        """
        Always set -drive property, it's mandatory. Also for hotplug purposes
        store this bus device into hook variable of the device.
        """
        self._set_device_props(device, addr)
        if hasattr(device, 'hook_drive_bus'):
            device.hook_drive_bus = self.get_device()


class QDenseBus(QSparseBus):

    """
    Dense bus representation. The only difference from SparseBus is the output
    string format. DenseBus iterates over all addresses and show free slots
    too. SparseBus on the other hand prints always the device address.
    """

    def _str_devices_long(self):
        """ Show all addresses even when they are unused """
        out = ""
        addr_pattern = [None] * len(self.addr_items)
        addr = self._set_first_addr(addr_pattern)[0]
        while addr:
            dev = self.bus.get(self._addr2stor(addr))
            out += '%s< %4s >%s\n  ' % ('-' * 15, self._addr2stor(addr),
                                        '-' * 15)
            if hasattr(dev, 'str_long'):
                out += dev.str_long().replace('\n', '\n  ')
                out = out[:-3]
            elif isinstance(dev, six.string_types):
                out += '"%s"' % dev
            else:
                out += "%s" % dev
            out += '\n'
            addr = self._increment_addr(addr_pattern, addr)
        return out

    def _str_devices(self):
        """ Show all addresses even when they are unused, don't print addr """
        out = '['
        addr_pattern = [None] * len(self.addr_items)
        addr = self._set_first_addr(addr_pattern)[0]
        while addr:
            out += "%s," % self.bus.get(self._addr2stor(addr))
            addr = self._increment_addr(addr_pattern, addr)
        if out[-1] == ',':
            out = out[:-1]
        return out + ']'


class QPCIBus(QSparseBus):

    """
    PCI Bus representation (bus&addr, uses hex digits)
    """

    def __init__(self, busid, bus_type, aobject=None, length=32, first_port=0):
        """ bus&addr, 32 slots """
        super(QPCIBus, self).__init__('bus', [['addr', 'func'], [length, 8]],
                                      busid, bus_type, aobject)
        self.first_port = (first_port, 0)

    @staticmethod
    def _addr2stor(addr):
        """ force all items as hexadecimal values """
        out = ""
        for value in addr:
            if value is None:
                out += '*-'
            else:
                out += '0x%x-' % value
        if out:
            return out[:-1]
        else:
            return "*"

    def _dev2addr(self, device):
        """ Read the values in base of 16 (hex) """
        addr = device.get_param('addr')
        if isinstance(addr, int):     # only addr
            return [addr, 0]
        elif not addr:    # not defined
            return [None, 0]
        elif isinstance(addr, six.string_types):     # addr or addr.func
            addr = [int(_, 16) for _ in addr.split('.', 1)]
            if len(addr) < 2:   # only addr
                addr.append(0)
        return addr

    def _set_device_props(self, device, addr):
        """ Convert addr to the format used by qtree """
        device.set_param(self.bus_item, self.busid)
        orig_addr = device.get_param('addr')
        if addr[1] or (isinstance(orig_addr, six.string_types) and
                       orig_addr.find('.') != -1):
            device.set_param('addr', '%s.%s' % (hex(addr[0]), hex(addr[1])))
        else:
            device.set_param('addr', '%s' % hex(addr[0]))

    def _update_device_props(self, device, addr):
        """ Always set properties """
        self._set_device_props(device, addr)

    def _increment_addr(self, addr, last_addr=None):
        """ Don't use multifunction address by default """
        if addr[1] is None:
            addr[1] = 0
        return super(QPCIBus, self)._increment_addr(addr, last_addr=last_addr)


class QPCIEBus(QPCIBus):
    """
    PCIE root bus representation (creates pcie-root-port for virtio pci
    device by default.)
    """

    def __init__(self, busid, bus_type, root_port_type,
                 aobject=None, root_port_params=None):
        """
        :param busid: id of the bus (pcie.0)
        :param bus_type: type of the bus (PCIE)
        :param root_port_type: root port type
        :param aobject: Related autotest object (pci.0)
        :param root_port_params: root port params
        """
        super(QPCIEBus, self).__init__(busid, bus_type, aobject)
        self.__root_ports = {}
        self.__root_port_type = root_port_type
        self.__root_port_params = root_port_params
        self.__last_port_index = [0]

    def is_direct_plug(self, device):
        """
        Justify if the device should be plug to pcie bus directly,
        the device is not directly plugged only if it is a virtio
        pci device and the device param pcie_direct_plug is "no".

        :param device: the QBaseDevice object
        :return: bool value for directly plug or not.
        """
        not_direct_plug = device.get_param("pcie_direct_plug", "no") == "no"
        if not_direct_plug and device.is_pcie_device():
            return False
        return True

    def _get_port_addr(self, root_port):
        """
        Get root port address for function port

        :param root_port: pcie-root-port QDevice object
        :return string: pcie-root-port address or None if slot is full
        """
        slot = root_port.get_param('addr').split('.')[0]
        full_addrs = set(['%s.%s' % (slot, hex(_)) for _ in range(1, 8)])
        used_addrs = set(self.__root_ports.keys())
        try:
            return sorted(list(full_addrs - used_addrs))[0]
        except IndexError:
            pass
        return None

    def add_root_port(self, root_port_type, root_port=None,
                      root_port_params=None):
        """
        Add pcie root port to the bus and __root_ports list, assign free slot,
        chassis, and addr for it according to current list.

        :param root_port_type: root port type
        :param root_port: pcie-root-port QDevice object
        :param root_port_params: root port params
        :return: pcie-root-port QDevice object
        """
        if not root_port:
            root_port = self._add_root_port(root_port_type, root_port_params)
            root_port.set_param('multifunction', 'on')
            self.insert(root_port)
        else:
            addr = self._get_port_addr(root_port)
            root_port = self._add_root_port(root_port_type, root_port_params)
            root_port.set_param('addr', addr)
            self.insert(root_port)
        return root_port

    def _add_root_port(self, root_port_type, root_port_params=None):
        """
        Generate pcie-root-port QDevice object with certain addr and id

        :param root_port_type: root port type
        :param root_port_params: root port params
        :return: pcie-root-port QDevice object
        """
        index = self.__last_port_index[0] + 1
        self.__last_port_index = [index]
        bus_id = "%s-%s" % (root_port_type, index)
        bus = QPCIBus(bus_id, 'PCIE', bus_id, length=1, first_port=0)
        parent_bus = {'busid': '_PCI_CHASSIS'}
        params = {'id': bus_id, 'port': hex(index)}
        if root_port_params:
            for extra_param in root_port_params.split(","):
                key, value = extra_param.split('=')
                params[key] = value
        root_port = QDevice(root_port_type,
                            params,
                            aobject=bus_id,
                            parent_bus=parent_bus,
                            child_bus=bus)
        return root_port

    def _insert(self, device, addr):
        """
        Inserts a pcie-root-port before the device if it is not a
        direct plug device.

        :param device: qdevice.QDevice object
        :param addr: addr to insert the device
        """
        if device.get_param('driver') == self.__root_port_type:
            key = addr.replace('-', '.')
            self.__root_ports[key] = device
            device.set_param('bus', self.aobject)
            return super(QPCIEBus, self)._insert(device, addr)

        if self.is_direct_plug(device):
            return super(QPCIEBus, self)._insert(device, addr)

        added_devices = []
        root_port = self.prepare_free_root_port()
        added_devices.append(root_port)
        bus = added_devices[-1].child_bus[0]
        device['bus'] = bus.busid
        bus.insert(device)
        return added_devices

    def _set_device_props(self, device, addr):
        """
        For indirect device, insert the device into the pcie port port instead
        of setting the addr.

        :param device: pcie-root-port QDevice object
        :param addr: addr to insert the device
        """
        if self.is_direct_plug(device):
            super(QPCIEBus, self)._set_device_props(device, addr)

    def get_root_port_by_params(self, filt=None):
        """
        Get root ports by given dict

        :filt: dict to get root port
        :return: list of root ports
        """
        out = []
        for root_port in self.__root_ports.values():
            if filt:
                for key, value in six.iteritems(filt):
                    if key not in root_port.params:
                        continue
                    if root_port.get_param(key) != value:
                        continue
            out.append(root_port)
        return out

    def prepare_free_root_port(self):
        """
        Return pcie root port for plugin a pcie device

        :return: QDevice object, pcie-root-port device
        """
        root_ports = self.get_root_port_by_params({'multifunction': 'on'})
        # sort root ports to ensure continuity of port addresses
        root_ports = sorted(root_ports, key=lambda x: x.get_param('addr'))
        for root_port in root_ports:
            addr = self._get_port_addr(root_port)
            if addr is not None:
                return self.add_root_port(self.__root_port_type, root_port,
                                          self.__root_port_params)
        return self.add_root_port(self.__root_port_type, None,
                                  self.__root_port_params)

    def get_free_root_port(self):
        """
        Get free root port.
        """
        for root_port in self.__root_ports.values():
            child_bus = root_port.child_bus[0]
            if len(child_bus.bus) < child_bus.addr_lengths[0]:
                return root_port
        return None

    def prepare_hotplug(self, device):
        """
        Prepares a device to be hot-plugged into this bus;
        You need to call "insert" afterwards. Concurrent calls
        of "prepare_hotplug" and "insert" are not supported
        :param device: The QDevice object
        """
        root_port = self.get_free_root_port()
        bus = root_port.child_bus[0]
        device.set_param("bus", bus.busid)
        parent_bus = device.parent_bus
        if not isinstance(parent_bus, (tuple, list)):
            device.parent_bus = [device.parent_bus]
            return
        device.parent_bus = ({"busid": bus.busid},) + \
            tuple(bus for bus in parent_bus if not self.match_bus(bus))
        return


class QPCISwitchBus(QPCIBus):

    """
    PCI Switch bus representation (creates downstream device while inserting
    a device).
    """

    def __init__(self, busid, bus_type, downstream_type, aobject=None):
        super(QPCISwitchBus, self).__init__(busid, bus_type, aobject)
        self.__downstream_ports = {}
        self.__downstream_type = downstream_type

    def add_downstream_port(self, addr):
        """
        Add downstream port of the certain address
        """
        if addr not in self.__downstream_ports:
            _addr = int(addr, 16)
            bus_id = "%s.%s" % (self.busid, _addr)
            bus = QPCIBus(bus_id, 'PCIE', bus_id)
            self.__downstream_ports["0x%x" % _addr] = bus
            downstream = QDevice(self.__downstream_type,
                                 {'id': bus_id,
                                  'bus': self.busid,
                                  'addr': "0x%x" % _addr},
                                 aobject=self.aobject,
                                 parent_bus={'busid': '_PCI_CHASSIS'},
                                 child_bus=bus)
            return downstream

    def _insert(self, device, addr):
        """
        Instead of the device inserts the downstream port. The device is
        inserted later during _set_device_props into this downstream port.
        """
        _addr = addr.split('-')[0]
        added_devices = []
        downstream = self.add_downstream_port(_addr)
        if downstream is not None:
            added_devices.append(downstream)
            added_devices.extend(super(QPCISwitchBus, self)._insert(downstream,
                                                                    addr))

        bus_id = "%s.%s" % (self.busid, int(_addr, 16))
        device['bus'] = bus_id

        return added_devices

    def _set_device_props(self, device, addr):
        """
        Instead of setting the addr this insert the device into the
        downstream port.
        """
        self.__downstream_ports['0x%x' % addr[0]].insert(device)


class QSCSIBus(QSparseBus):

    """
    SCSI bus representation (bus + 2 leves, don't iterate over lun by default)
    """

    def __init__(self, busid, bus_type, addr_spec, aobject=None, atype=None):
        """
        :param busid: id of the bus (mybus.0)
        :param bus_type: type of the bus (virtio-scsi-pci, lsi53c895a, ...)
        :param addr_spec: Ranges of addr_spec [scsiid_range, lun_range]
        :param aobject: Related autotest object (image1)
        :param atype: Autotest bus type
        :type atype: str
        """
        super(QSCSIBus, self).__init__('bus', [['scsi-id', 'lun'], addr_spec],
                                       busid, bus_type, aobject, atype)

    def _increment_addr(self, addr, last_addr=None):
        """
        Qemu doesn't increment lun automatically so don't use it when
        it's not explicitly specified.
        """
        if addr[1] is None:
            addr[1] = 0
        return super(QSCSIBus, self)._increment_addr(addr, last_addr=last_addr)


class QBusUnitBus(QDenseBus):

    """ Implementation of bus-unit/nr bus (ahci, ide, virtio-serial) """

    def __init__(self, busid, bus_type, lengths, aobject=None, atype=None, unit_spec='unit'):
        """
        :param busid: id of the bus (mybus.0)
        :type busid: str
        :param bus_type: type of the bus (ahci)
        :type bus_type: str
        :param lengths: lengths of [buses, units]
        :type lengths: builtin.list
        :param aobject: Related autotest object (image1)
        :type aobject: str
        :param atype: Autotest bus type
        :type atype: str
        """
        if len(lengths) != 2:
            raise ValueError("len(lengths) have to be 2 (%s)" % self)
        super(QBusUnitBus, self).__init__('bus', [['bus', unit_spec], lengths],
                                          busid, bus_type, aobject, atype)
        self.unit_spec = unit_spec

    def _update_device_props(self, device, addr):
        """ Always set the properties """
        return self._set_device_props(device, addr)

    def _set_device_props(self, device, addr):
        """This bus is compound of m-buses + n-units, set properties """
        device.set_param('bus', "%s.%s" % (self.busid, addr[0]))
        device.set_param(self.unit_spec, addr[1])

    def _check_bus(self, device):
        """ This bus is compound of m-buses + n-units, check correct busid """
        bus = device.get_param('bus')
        if isinstance(bus, six.string_types):
            bus = bus.rsplit('.', 1)
            if len(bus) == 2 and bus[0] != self.busid:  # aaa.3
                return False
            elif not bus[0].isdigit() and bus[0] != self.busid:     # aaa
                return False
        return True  # None, 5, '3'

    def _dev2addr(self, device):
        """ This bus is compound of m-buses + n-units, parse addr from dev """
        bus = None
        unit = None
        busid = device.get_param('bus')
        if isinstance(busid, six.string_types):
            if busid.isdigit():
                bus = int(busid)
            else:
                busid = busid.rsplit('.', 1)
                if len(busid) == 2 and busid[1].isdigit():
                    bus = int(busid[1])
        if isinstance(busid, int):
            bus = busid
        if device.get_param(self.unit_spec):
            unit = int(device.get_param(self.unit_spec))
        return [bus, unit]


class QSerialBus(QBusUnitBus):

    """ Serial bus representation """

    def __init__(self, busid, bus_type, aobject=None, max_ports=32):
        """
        :param busid: bus id
        :param bus_type: bus type(virtio-serial-device, virtio-serial-pci)
        :param aobject: autotest object
        :param max_ports: max ports, default 32
        """

        super(QSerialBus, self).__init__(busid, 'SERIAL', [1, max_ports],
                                         aobject, bus_type, unit_spec='nr')
        self.first_port = (0, 1)


class QAHCIBus(QBusUnitBus):

    """ AHCI bus (ich9-ahci, ahci) """

    def __init__(self, busid, aobject=None):
        """ 6xbus, 2xunit """
        super(QAHCIBus, self).__init__(busid, 'IDE', [6, 1], aobject, 'ahci')


class QIDEBus(QBusUnitBus):

    """ IDE bus (piix3-ide) """

    def __init__(self, busid, aobject=None):
        """ 2xbus, 2xunit """
        super(QIDEBus, self).__init__(busid, 'IDE', [2, 2], aobject, 'ide')


class QFloppyBus(QDenseBus):

    """
    Floppy bus (-global isa-fdc.drive?=$drive)
    """

    def __init__(self, busid, aobject=None):
        """ property <= [driveA, driveB] """
        super(QFloppyBus, self).__init__(None, [['property'], [2]], busid,
                                         'floppy', aobject)

    @staticmethod
    def _addr2stor(addr):
        """ translate as drive$CHAR """
        return "drive%s" % chr(65 + addr[0])  # 'A' + addr

    def _dev2addr(self, device):
        """ Read None, number or drive$CHAR and convert to int() """
        addr = device.get_param('property')
        if isinstance(addr, six.string_types):
            if addr.startswith('drive') and len(addr) > 5:
                addr = ord(addr[5])
            elif addr.isdigit():
                addr = int(addr)
        return [addr]

    def _update_device_props(self, device, addr):
        """ Always set props """
        self._set_device_props(device, addr)

    def _set_device_props(self, device, addr):
        """ Change value to drive{A,B,...} """
        device.set_param('property', self._addr2stor(addr))


class QOldFloppyBus(QDenseBus):

    """
    Floppy bus (-drive index=n)
    """

    def __init__(self, busid, aobject=None):
        """ property <= [driveA, driveB] """
        super(QOldFloppyBus, self).__init__(None, [['index'], [2]], busid,
                                            'floppy', aobject)

    def _update_device_props(self, device, addr):
        """ Always set props """
        self._set_device_props(device, addr)

    def _set_device_props(self, device, addr):
        """ Change value to drive{A,B,...} """
        device.set_param('index', self._addr2stor(addr))


class QCPUBus(QSparseBus):
    """
    CPU virtual bus representation.
    """

    def __init__(self, cpu_model, addr_spec, aobject=None, atype=None):
        """
        :param cpu_model: cpu model name
        :type cpu_model: str
        """
        super(QCPUBus, self).__init__(None, addr_spec, "vcpu_bus", cpu_model,
                                      aobject, atype)
        self.vcpus_count = 0

    def _str_devices(self):
        """
        short string representation of the bus, will ignore all reserved slot
        """
        out = '{'
        for addr in sorted(self.bus.keys(), key=lambda x: "{0:0>8}".format(x)):
            if self.bus[addr] != "reserved":
                out += "%s:%s, " % (addr, self.bus[addr])
        return out.rstrip(", ") + '}'

    def _str_devices_long(self):
        """
        long string representation of the bus, will ignore all reserved slot
        """
        out = ""
        for addr in sorted(self.bus.keys(), key=lambda x: "{0:0>8}".format(x)):
            dev = self.bus[addr]
            if dev != "reserved":
                if not dev.is_enabled():
                    addr += " idled"
                out += "%s< %s >%s\n  " % ("-" * 15, addr.center(10), "-" * 15)
                out += dev.str_long().replace('\n', '\n  ')
                out = out.rstrip()
            out += '\n'
        return out.rstrip()

    def _update_device_props(self, device, addr):
        """ Always set properties """
        return self._set_device_props(device, addr)

    def initialize(self, cpuinfo):
        """
        Use full cpu information to reinitialize.
        :param cpuinfo: virt_vm.CpuInfo Object
        """
        if cpuinfo.qemu_type == "spapr" or "s390" in cpuinfo.qemu_type:
            self.vcpus_count = 1
            self.addr_items = ["core-id"]
            self.addr_lengths = [cpuinfo.maxcpus]
            self.first_port = [range(cpuinfo.maxcpus)[cpuinfo.smp]]
            if cpuinfo.qemu_type == "spapr":
                self.vcpus_count = cpuinfo.threads
                next_addr = list(self.first_port)
                while next_addr is not False:
                    if next_addr[0] % self.vcpus_count != 0:
                        self.reserve(next_addr)
                    next_addr = self._increment_addr([None], next_addr)
        else:
            self.vcpus_count = 1
            self.addr_items = ["socket-id", "core-id", "thread-id"]
            self.addr_lengths = [cpuinfo.sockets, cpuinfo.cores,
                                 cpuinfo.threads]
            self.first_port = [[s, c, t] for s in range(cpuinfo.sockets)
                               for c in range(cpuinfo.cores)
                               for t in range(cpuinfo.threads)][cpuinfo.smp]
            if cpuinfo.dies != 0:
                self.addr_items.insert(1, "die-id")
                self.addr_lengths.insert(1, cpuinfo.dies)
                self.first_port = [[s, d, c, t] for s in range(cpuinfo.sockets)
                                   for d in range(cpuinfo.dies)
                                   for c in range(cpuinfo.cores)
                                   for t in range(cpuinfo.threads)][cpuinfo.smp]


class QThrottleGroupBus(QSparseBus):
    """ThrottleGroup virtual bus."""

    def __init__(self, throttle_group_id):
        """
        ThrottleGroup bus constructor.

        :param throttle_group_id: related ThrottleGroup object id
        """
        super(QThrottleGroupBus, self).__init__("throttle-group", [[], []],
                                                "%s" % throttle_group_id,
                                                "ThrottleGroup",
                                                throttle_group_id)

    def get_free_slot(self, addr_pattern):
        """Return the device id as unoccupied address."""
        return addr_pattern

    def _dev2addr(self, device):
        """Return the device id as address."""
        return [device.get_qid()]


class QIOThreadBus(QSparseBus):
    """IOThread virtual bus."""

    def __init__(self, iothread_id):
        """
        iothread bus constructor.

        :param iothread_id: related QIOThread object id
        """
        super(QIOThreadBus, self).__init__("iothread", [[], []],
                                           "iothread_bus_%s" % iothread_id,
                                           "IOTHREAD", iothread_id)

    def _check_bus(self, device):
        """Check if the device is pluggable."""
        iothread = device.get_param(self.bus_item)
        return iothread is None or iothread == self.get_device().get_qid()

    def _dev2addr(self, device):
        """Return the device id as address."""
        return [device.get_qid()]

    def get_free_slot(self, addr_pattern):
        """Return the device id as unoccupied address."""
        return addr_pattern

    def _set_device_props(self, device, addr):
        """Set device iothread param."""
        device.set_param(self.bus_item, self.get_device().get_qid())

    def _update_device_props(self, device, addr):
        """Always set device iothread param."""
        self._set_device_props(device, addr)


class QUnixSocketBus(QSparseBus):
    """
    Unix Socket pseudo bus.
    """

    def __init__(self, busid, aobject):
        super(QUnixSocketBus, self).__init__("path", [[], []], busid,
                                             "QUnixSocketBus", aobject)

    def _update_device_props(self, device, addr):
        """Update device properties."""
        self._set_device_props(device, addr)
