"""
Autotest qdev-structure representation.

This is the main class which represent qdev-structure. It allows to create,
interact and verify the qemu qdev structure.

:copyright: 2012-2013 Red Hat Inc.
"""

# Python imports
from __future__ import division
import logging
import re
import os
import shutil
import stat
import json
import uuid

# Avocado imports
from avocado.core import exceptions
from avocado.utils import process

import six
from six.moves import xrange

try:
    from collections.abc import Sequence
except ImportError:
    from collections import Sequence

# Internal imports
from virttest import vt_iothread
from virttest import utils_qemu
from virttest import arch, storage, data_dir, virt_vm
from virttest import qemu_storage
from virttest.qemu_devices import qdevices
from virttest.qemu_devices.utils import (DeviceError, DeviceHotplugError,
                                         DeviceInsertError, DeviceRemoveError,
                                         DeviceUnplugError, none_or_int)
from virttest.utils_params import Params
from virttest.qemu_capabilities import Flags, Capabilities
from virttest.utils_version import VersionInterval

#
# Device container (device representation of VM)
# This class represents VM by storing all devices and their connections (buses)
#


class DevContainer(object):

    """
    Device container class
    """
    # General methods

    cache_map = {'writeback': {'write-cache': 'on',
                               'cache.direct': 'off',
                               'cache.no-flush': 'off'},
                 'none': {'write-cache': 'on',
                          'cache.direct': 'on',
                          'cache.no-flush': 'off'},
                 'writethrough': {'write-cache': 'off',
                                  'cache.direct': 'off',
                                  'cache.no-flush': 'off'},
                 'directsync': {'write-cache': 'off',
                                'cache.direct': 'on',
                                'cache.no-flush': 'off'},
                 'unsafe': {'write-cache': 'on',
                            'cache.direct': 'off',
                            'cache.no-flush': 'on'}}

    BLOCKDEV_VERSION_SCOPE = '[2.12.0, )'
    SMP_DIES_VERSION_SCOPE = '[4.1.0, )'

    def __init__(self, qemu_binary, vmname, strict_mode="no",
                 workaround_qemu_qmp_crash="no", allow_hotplugged_vm="yes"):
        """
        :param qemu_binary: qemu binary
        :param vm: related VM
        :param strict_mode: Use strict mode (set optional params)
        """
        def get_hmp_cmds(qemu_binary):
            """ :return: list of human monitor commands """
            _ = process.run("echo -e 'help\nquit' | %s -monitor "
                            "stdio -vnc none -S" % qemu_binary,
                            timeout=10, ignore_status=True,
                            shell=True, verbose=False).stdout_text
            _ = re.findall(r'^([^()\|\[\sA-Z]+\|?\w+)', _, re.M)
            hmp_cmds = []
            for cmd in _:
                if '|' not in cmd:
                    if cmd != 'The':
                        hmp_cmds.append(cmd)
                else:
                    hmp_cmds.extend(cmd.split('|'))
            return hmp_cmds

        def get_qmp_cmds(qemu_binary, workaround_qemu_qmp_crash=False):
            """ :return: list of qmp commands """
            cmds = None
            if not workaround_qemu_qmp_crash:
                cmds = process.run('echo -e \''
                                   '{ "execute": "qmp_capabilities" }\n'
                                   '{ "execute": "query-commands", "id": "RAND91" }\n'
                                   '{ "execute": "quit" }\''
                                   '| %s -qmp stdio -vnc none -S | grep return |'
                                   ' grep RAND91' % qemu_binary, timeout=10,
                                   ignore_status=True, shell=True,
                                   verbose=False).stdout_text.splitlines()
            if not cmds:
                # Some qemu versions crashes when qmp used too early; add sleep
                cmds = process.run('echo -e \''
                                   '{ "execute": "qmp_capabilities" }\n'
                                   '{ "execute": "query-commands", "id": "RAND91" }\n'
                                   '{ "execute": "quit" }\' | (sleep 1; cat )'
                                   '| %s -qmp stdio -vnc none -S | grep return |'
                                   ' grep RAND91' % qemu_binary, timeout=10,
                                   ignore_status=True, shell=True,
                                   verbose=False).stdout_text.splitlines()
            if cmds:
                cmds = re.findall(r'{\s*"name"\s*:\s*"([^"]+)"\s*}', cmds[0])
            if cmds:    # If no mathes, return None
                return cmds

        self.__state = -1    # -1 synchronized, 0 synchronized after hotplug
        self.__qemu_binary = qemu_binary
        self.__execute_qemu_last = None
        self.__execute_qemu_out = ""
        # Check whether we need to add machine_type
        cmd = "%s -device \? 2>&1" % qemu_binary
        result = process.run(cmd, timeout=10,
                             ignore_status=True,
                             shell=True,
                             verbose=False)
        # Some architectures (arm) require machine type to be always set
        if result.exit_status and b"machine specified" in result.stdout:
            self.__workaround_machine_type = True
            basic_qemu_cmd = "%s -machine virt" % qemu_binary
        else:
            self.__workaround_machine_type = False
            basic_qemu_cmd = qemu_binary
        self.__qemu_help = self.execute_qemu("-help", 10)
        # escape the '?' otherwise it will fail if we have a single-char
        # filename in cwd
        self.__device_help = self.execute_qemu("-device \? 2>&1", 10)
        self.__machine_types = process.run("%s -M \?" % qemu_binary,
                                           timeout=10,
                                           ignore_status=True,
                                           shell=True,
                                           verbose=False).stdout_text
        self.__hmp_cmds = get_hmp_cmds(basic_qemu_cmd)
        self.__qmp_cmds = get_qmp_cmds(basic_qemu_cmd,
                                       workaround_qemu_qmp_crash == 'always')
        self.vmname = vmname
        self.strict_mode = strict_mode == 'yes'
        self.__devices = []
        self.__buses = []
        self.allow_hotplugged_vm = allow_hotplugged_vm == 'yes'
        self.caps = Capabilities()
        self._probe_capabilities()
        self.__iothread_manager = None
        self.__iothread_supported_devices = set()
        self.temporary_image_snapshots = set()

    def initialize_iothread_manager(self, params, guestcpuinfo):
        """Initialize iothread manager.
        :param params: vt params
        :param guestcpuinfo: Cpuinfo object that stores guest cpu info
        """
        iothreads_lst = params.objects("iothreads")
        iothread_scheme = params.get("iothread_scheme")

        if iothread_scheme == "oto":
            iothreads_lst = []
        elif iothread_scheme == "rhv":
            iothreads_lst = iothreads_lst[:1] or ["iothread0"]

        iothread_props = {"iothread_poll_max_ns": "poll-max-ns"}
        iothreads = []
        for iothread in iothreads_lst:
            iothread_params = params.object_params(iothread)
            iothread_dict = {
                iothread_props[prop]: iothread_params[prop]
                for prop in iothread_props if prop in iothread_params
            }
            iothread = qdevices.QIOThread(iothread_id=iothread,
                                          params=iothread_dict)
            iothreads.append(iothread)

        scheme_to_manager = {
            "": vt_iothread.PredefinedManager,
            "roundrobin": vt_iothread.RoundRobinManager,
            "oto": vt_iothread.OTOManager,
            "rhv": vt_iothread.RoundRobinManager,
        }
        manager = scheme_to_manager.get(iothread_scheme,
                                        vt_iothread.PredefinedManager)

        self.insert(iothreads)

        self.__iothread_manager = manager(iothreads)

    def is_dev_iothread_supported(self, device):
        """Check if dev supports iothread.
        :param device: device to check
        :type device: QDevice or string
        """
        try:
            device = device.get_param("driver")
        except AttributeError:
            if not isinstance(device, six.string_types):
                raise TypeError("device: expected string or QDevice")
        if not device:
            return False
        if device in self.__iothread_supported_devices:
            return True
        options = "--device %s,\\?" % device
        out = self.execute_qemu(options)
        if "iothread" in out:
            self.__iothread_supported_devices.add(device)
            return True
        return False

    def allocate_iothread(self, iothread, device):
        """
        Allocate iothread for device to use.

        :param iothread: iothread specified in params
                         could be:
                         'auto': allocate iothread based on schems specified by
                                 'iothread_scheme'.
                         iothread id: request specific iothread to use.
        :param device: device object
        :return: iothread object allocated
        """
        if self.is_dev_iothread_supported(device):
            iothread = self.__iothread_manager.request_iothread(iothread)
            dev_iothread_parent = {"busid": iothread.iothread_bus.busid}
            if device.parent_bus:
                if isinstance(device.parent_bus, Sequence):
                    device.parent_bus += (dev_iothread_parent,)
                else:
                    device.parent_bus = \
                        (device.parent_bus, dev_iothread_parent)
            else:
                device.parent_bus = (dev_iothread_parent,)
            return iothread
        else:
            err_msg = "Device %s(%s) not support iothread" % \
                (device.get_aid(), device.get_param("driver"))
            raise TypeError(err_msg)

    def _probe_capabilities(self):
        """ Probe capabilities. """
        ver = utils_qemu.get_qemu_version(self.__qemu_binary)[0]

        # -blockdev
        if (self.has_option('blockdev') and
                ver in VersionInterval(self.BLOCKDEV_VERSION_SCOPE)):
            self.caps.set_flag(Flags.BLOCKDEV)
        # -smp dies=?
        if ver in VersionInterval(self.SMP_DIES_VERSION_SCOPE):
            self.caps.set_flag(Flags.SMP_DIES)
        # -incoming defer
        if self.has_option('incoming defer'):
            self.caps.set_flag(Flags.INCOMING_DEFER)

    def __getitem__(self, item):
        """
        :param item: autotest id or QObject-like object
        :return: First matching object defined in this QDevContainer
        :raise KeyError: In case no match was found
        """
        if isinstance(item, qdevices.QBaseDevice):
            if item in self.__devices:
                return item
        elif item:
            for device in self.__devices:
                if device.get_aid() == item:
                    return device
        raise KeyError("Device %s is not in %s" % (item, self))

    def get(self, item):
        """
        :param item: autotest id or QObject-like object
        :return: First matching object defined in this QDevContainer or None
        """
        if item in self:
            return self[item]

    def get_by_properties(self, filt):
        """
        Return list of matching devices
        :param filt: filter {'property': 'value', ...}
        :type filt: dict
        """
        out = []
        for device in self.__devices:
            for key, value in six.iteritems(filt):
                if not hasattr(device, key):
                    break
                if getattr(device, key) != value:
                    break
            else:
                out.append(device)
        return out

    def get_by_params(self, filt):
        """
        Return list of matching devices
        :param filt: filter {'param': 'value', ...}
        :type filt: dict
        """
        out = []
        for device in self.__devices:
            for key, value in six.iteritems(filt):
                if key not in device.params:
                    break
                if device.params[key] != value:
                    break
            else:
                out.append(device)
        return out

    def __delitem__(self, item):
        """
        Delete specified item from devices list
        :param item: autotest id or QObject-like object
        :raise KeyError: In case no match was found
        """
        # Remove child_buses including devices
        if self.remove(item):
            raise KeyError(item)

    def remove(self, device, recursive=True):
        """
        Remove device from this representation
        :param device: autotest id or QObject-like object
        :param recursive: remove children recursively
        :return: None on success, -1 when the device is not present
        """
        device = self[device]
        if not recursive:   # Check if there are no children
            for bus in device.child_bus:
                if len(bus) != 0:
                    raise DeviceRemoveError(device, "Child bus contains "
                                            "devices", self)
        else:               # Recursively remove all devices
            for dev in device.get_children():
                # One child might be already removed from other child's bus
                if dev in self:
                    self.remove(dev, True)
        if device in self.__devices:    # It might be removed from child bus
            for bus in self.__buses:        # Remove from parent_buses
                bus.remove(device)
            for bus in device.child_bus:    # Remove child buses from vm buses
                self.__buses.remove(bus)
            self.__devices.remove(device)   # Remove from list of devices

        if isinstance(device, qdevices.QIOThread):
            self.__iothread_manager.release_iothread(device)

    def wash_the_device_out(self, device):
        """
        Removes any traces of the device from representation.
        :param device: qdevices.QBaseDevice device
        """
        # remove device from parent buses
        for bus in self.__buses:
            if device in bus:
                bus.remove(device)
        # remove child devices
        for bus in device.child_bus:
            for dev in device.get_children():
                if dev in self:
                    self.remove(dev, True)
            # remove child_buses from self.__buses
            if bus in self.__buses:
                self.__buses.remove(bus)
        # remove device from self.__devices
        if device in self.__devices:
            self.__devices.remove(device)

    def __len__(self):
        """ :return: Number of inserted devices """
        return len(self.__devices)

    def __contains__(self, item):
        """
        Is specified item defined in current devices list?
        :param item: autotest id or QObject-like object
        :return: True - yes, False - no
        """
        if isinstance(item, qdevices.QBaseDevice):
            if item in self.__devices:
                return True
        elif item:
            for device in self.__devices:
                if device.get_aid() == item:
                    return True
        return False

    def __iter__(self):
        """ Iterate over all defined devices. """
        return self.__devices.__iter__()

    def __eq__(self, qdev2):
        """ Are the VM representation alike? """
        if len(qdev2) != len(self):
            return False
        if qdev2.get_state() != self.get_state():
            if qdev2.allow_hotplugged_vm:
                if qdev2.get_state() > 0 or self.get_state() > 0:
                    return False
            else:
                return False
        for dev in self:
            if dev not in qdev2:
                return False

        # state, buses and devices are handled earlier
        qdev2 = qdev2.__dict__
        for key, value in six.iteritems(self.__dict__):
            if key in ("_DevContainer__devices", "_DevContainer__buses",
                       "_DevContainer__state", "caps", "allow_hotplugged_vm",
                       "_DevContainer__iothread_manager",
                       "_DevContainer__iothread_supported_devices",
                       "temporary_image_snapshots"):
                continue
            if key not in qdev2 or qdev2[key] != value:
                return False
        return True

    def __ne__(self, qdev2):
        """ Are the VM representation different? """
        return not self.__eq__(qdev2)

    def set_dirty(self):
        """ Increase VM dirtiness (not synchronized with VM) """
        if self.__state >= 0:
            self.__state += 1
        else:
            self.__state = 1

    def set_clean(self):
        """ Decrease VM dirtiness (synchronized with VM) """
        if self.__state > 0:
            self.__state -= 1
        else:
            raise DeviceError("Trying to clean clear VM (probably calling "
                              "hotplug_clean() twice).\n%s" % self.str_long())

    def reset_state(self):
        """
        Mark representation as completely clean, without hotplugged devices.
        """
        self.__state = -1

    def get_state(self):
        """ Get the current state (0 = synchronized with VM) """
        return self.__state

    def get_by_qid(self, qid):
        """
        :param qid: qemu id
        :return: List of items with matching qemu id
        """
        ret = []
        if qid:
            for device in self:
                if device.get_qid() == qid:
                    ret.append(device)
        return ret

    def get_qdev_by_drive(self, device):
        """
        Get the qdev ID of device by drive name.

        :param device: device name
        :type device: str
        :return: the qdev ID
        :rtype: str
        """
        for dev in self.__devices:
            try:
                if isinstance(dev, qdevices.QDevice) and device == dev.params['drive']:
                    return dev.params['id']
            except KeyError:
                continue

    def str_short(self):
        """ Short string representation of all devices """
        out = "Devices of %s" % self.vmname
        dirty = self.get_state()
        if dirty == -1:
            pass
        elif dirty == 0:
            out += "(H)"
        else:
            out += "(DIRTY%s)" % dirty
        out += ": ["
        for device in self:
            out += "%s," % device
        if out[-1] == ',':
            out = out[:-1]
        return out + "]"

    def str_long(self):
        """ Long string representation of all devices """
        out = "Devices of %s" % self.vmname
        dirty = self.get_state()
        if dirty == -1:
            pass
        elif dirty == 0:
            out += "(H)"
        else:
            out += "(DIRTY%s)" % dirty
        out += ":\n"
        for device in self:
            out += device.str_long()
        if out[-1] == '\n':
            out = out[:-1]
        return out

    def str_bus_short(self):
        """ Short representation of all buses """
        out = "Buses of %s\n  " % self.vmname
        for bus in self.__buses:
            out += str(bus)
            out += "\n  "
        return out[:-3]

    def str_bus_long(self):
        """ Long representation of all buses """
        out = "Buses of %s:\n  " % self.vmname
        for bus in self.__buses:
            out += bus.str_long().replace('\n', '\n  ')
        return out[:-3]

    def __create_unique_aid(self, qid):
        """
        Creates unique autotest id name from given qid
        :param qid: Original qemu id
        :return: aid (the format is "$qid__%d")
        """
        if qid and qid not in self:
            return qid
        i = 0
        while "%s__%d" % (qid, i) in self:
            i += 1
        return "%s__%d" % (qid, i)

    def has_option(self, option):
        """
        :param option: Desired option
        :return: Is the desired option supported by current qemu?
        """
        return bool(re.search(r"^-%s(\s|$)" % option, self.__qemu_help,
                              re.MULTILINE))

    def has_device(self, device):
        """
        :param device: Desired device
        :return: Is the desired device supported by current qemu?
        """
        return bool(re.search(r'name "%s"|alias "%s"' % (device, device),
                              self.__device_help))

    def get_help_text(self):
        """
        :return: Full output of "qemu -help"
        """
        return self.__qemu_help

    def has_hmp_cmd(self, cmd):
        """
        :param cmd: Desired command
        :return: Is the desired command supported by this qemu's human monitor?
        """
        return cmd in self.__hmp_cmds

    def has_qmp_cmd(self, cmd):
        """
        :param cmd: Desired command
        :return: Is the desired command supported by this qemu's QMP monitor?
        """
        return cmd in self.__qmp_cmds

    def execute_qemu(self, options, timeout=5):
        """
        Execute this qemu and return the stdout+stderr output.
        :param options: additional qemu options
        :type options: string
        :param timeout: execution timeout
        :type timeout: int
        :return: Output of the qemu
        :rtype: string
        """
        if self.__execute_qemu_last != options:
            if self.__workaround_machine_type:
                cmd = "%s -machine virt %s 2>&1" % (self.__qemu_binary,
                                                    options)
            else:
                cmd = "%s %s 2>&1" % (self.__qemu_binary, options)
            result = process.run(cmd, timeout=timeout,
                                 ignore_status=True,
                                 shell=True,
                                 verbose=False)
            self.__execute_qemu_out = result.stdout_text
            self.__execute_qemu_last = options
        return self.__execute_qemu_out

    def get_buses(self, bus_spec, type_test=False):
        """
        :param bus_spec: Bus specification (dictionary)
        :type bus_spec: dict
        :param atype: Match qemu and atype params
        :type atype: bool
        :return: All matching buses
        :rtype: List of QSparseBus
        """
        buses = []
        for bus in self.__buses:
            if bus.match_bus(bus_spec, type_test):
                buses.append(bus)
        return buses

    def get_first_free_bus(self, bus_spec, addr):
        """
        :param bus_spec: Bus specification (dictionary)
        :param addr: Desired address
        :return: First matching bus with free desired address (the latest
                 added matching bus)
        """
        buses = self.get_buses(bus_spec)
        for bus in buses:
            _ = bus.get_free_slot(addr)
            if _ is not None and _ is not False:
                return bus

    def insert(self, devices, strict_mode=None):
        """
        Inserts devices into this VM representation
        :param devices: List of qdevices.QBaseDevice devices
        :raise DeviceError: On failure. The representation remains unchanged.
        """
        def cleanup():
            """ Remove all added devices (on failure) """
            for device in added:
                self.wash_the_device_out(device)

        if not isinstance(devices, list):
            devices = [devices]

        added = []
        for device in devices:
            try:
                added.extend(self._insert(device, strict_mode))
            except DeviceError as details:
                cleanup()
                raise DeviceError("%s\nError occurred while inserting device %s"
                                  " (%s). Please check the log for details."
                                  % (details, device, devices))
        return added

    def _insert(self, device, strict_mode=None):
        """
        Inserts device into this VM representation
        :param device: qdevices.QBaseDevice device
        :raise DeviceError: On failure. The representation remains unchanged.

        1)  get list of matching parent buses
        2)  try to find matching bus+address
        2b) add bus required additional devices prior to adding this device
        3)  add child buses
        4)  append into self.devices
        """
        def clean(device, added_devices):
            """ Remove all inserted devices (on failure) """
            self.wash_the_device_out(device)
            for device in added_devices:
                self.wash_the_device_out(device)

        if strict_mode is None:
            _strict_mode = self.strict_mode
        if strict_mode is True:
            _strict_mode = True
        else:
            _strict_mode = False
        added_devices = []
        if device.parent_bus is not None and not isinstance(device.parent_bus,
                                                            (list, tuple)):
            # it have to be list of parent buses
            device.parent_bus = (device.parent_bus,)
        for parent_bus in device.parent_bus:
            # type, aobject, busid
            if parent_bus is None:
                continue
            # 1
            buses = self.get_buses(parent_bus, True)
            if not buses:
                err = "ParentBus(%s): No matching bus\n" % parent_bus
                clean(device, added_devices)
                raise DeviceInsertError(device, err, self)
            bus_returns = []
            strict_mode = _strict_mode
            for bus in buses:   # 2
                if not bus.match_bus(parent_bus, False):
                    # First available bus in qemu is not of the same type as
                    # we in autotest require. Force strict mode to get this
                    # device into the correct bus (ide-hd could go into ahci
                    # and ide hba, qemu doesn't care, autotest does).
                    strict_mode = True
                    bus_returns.append(-1)  # Don't use this bus
                    continue
                bus_returns.append(bus.insert(device, strict_mode))
                if isinstance(bus_returns[-1], list):   # we are done
                    # The bus might require additional devices plugged first
                    try:
                        added_devices.extend(self.insert(bus_returns[-1]))
                    except DeviceError as details:
                        err = ("Can't insert device %s because additional "
                               "device required by bus %s failed to be "
                               "inserted with:\n%s" % (device, bus, details))
                        clean(device, added_devices)
                        raise DeviceError(err)
                    break
            if isinstance(bus_returns[-1], list):   # we are done
                continue
            err = "ParentBus(%s): No free matching bus\n" % parent_bus
            clean(device, added_devices)
            raise DeviceInsertError(device, err, self)
        # 3
        for bus in device.child_bus:
            self.__buses.insert(0, bus)
        # 4
        if device.get_qid() and self.get_by_qid(device.get_qid()):
            err = "Devices qid %s already used in VM\n" % device.get_qid()
            clean(device, added_devices)
            raise DeviceInsertError(device, err, self)
        device.set_aid(self.__create_unique_aid(device.get_qid()))
        self.__devices.append(device)
        added_devices.append(device)
        return added_devices

    def is_pci_device(self, device):
        """
        check if the device is plugged into pci bus
        :param device: device name
        :return: True if is pci device, otherwise False
        """
        return bool(re.search(
            r'name "%s", bus PCI|bus PCI, .*alias "%s"' % (device, device),
            self.__device_help))

    def simple_hotplug(self, device, monitor, bus=None):
        """
        Function hotplug device to devices representation. If verification is
        supported by hotplugged device and result of verification is True
        then it calls set_clean. Otherwise it don't call set_clean because
        devices representation don't know if device is added correctly.

        :param device: Device which should be hotplugged.
        :type device: string, qdevices.QDevice.
        :param monitor: Monitor from vm.
        :type monitor: qemu_monitor.Monitor
        :param bus: The bus to be plugged into
        :type bus: qdevice.QSparseBus
        :return: tuple(monitor.cmd(), verify_hotplug output)
        """
        self.set_dirty()

        if isinstance(device, qdevices.QDevice):
            if bus is None:
                if self.is_pci_device(device['driver']):
                    bus = self.get_buses({'aobject': 'pci.0'})[0]
                if not isinstance(device.parent_bus, (list, tuple)):
                    device.parent_bus = [device.parent_bus]
                for parent_bus in device.parent_bus:
                    for _bus in self.get_buses(parent_bus):
                        if _bus.bus_item == 'bus':
                            bus = _bus
                            break
            if bus is not None:
                bus.prepare_hotplug(device)

        try:
            # Insert the device first to assign slot
            qdev_out = self.insert(device)
            if not isinstance(qdev_out, list) or len(qdev_out) != 1:
                raise NotImplementedError("This device %s require to hotplug "
                                          "multiple devices, which is not "
                                          "supported." % device)
        except DeviceError as exc:
            raise DeviceHotplugError(device, 'According to qemu_device: %s'
                                     % exc, self)
        else:
            out = device.hotplug(monitor)
            ver_out = device.verify_hotplug(out, monitor)
            if ver_out is False:
                self.remove(device)
            self.set_clean()

        return out, ver_out

    def simple_unplug(self, device, monitor, timeout=30):
        """
        Function unplug device to devices representation. If verification is
        supported by unplugged device and result of verification is True
        then it calls set_clean. Otherwise it don't call set_clean because
        devices representatio don't know if device is added correctly.

        :param device: Device which should be unplugged.
        :type device: string, qdevices.QDevice.
        :param monitor: Monitor from vm.
        :type monitor: qemu_monitor.Monitor
        :param timeout: execution timeout
        :type timeout: int
        :return: tuple(monitor.cmd(), verify_unplug output)
        """
        device = self[device]
        self.set_dirty()
        # Remove all devices, which are removed together with this dev
        out = device.unplug(monitor)

        # The unplug action sometimes delays for a while per host performance,
        # it will be accepted if the unplug been accomplished within 30s
        from virttest import utils_misc
        if not utils_misc.wait_for(
                lambda: device.verify_unplug(out, monitor) is True,
                first=1, step=5, timeout=timeout):
            self.set_clean()
            return out, device.verify_unplug(out, monitor)

        ver_out = device.verify_unplug(out, monitor)

        try:
            device.unplug_hook()
            drive = device.get_param("drive")
            if drive:
                if Flags.BLOCKDEV in self.caps:
                    format_node = self[drive]
                    nodes = [format_node]
                    nodes.extend((n for n in format_node.get_child_nodes()))
                    for node in nodes:
                        if not node.verify_unplug(node.unplug(monitor), monitor):
                            raise DeviceUnplugError(
                                node, "Failed to unplug blockdev node.", self)
                        self.remove(node, True if isinstance(
                            node, qdevices.QBlockdevFormatNode) else False)
                        if not isinstance(node, qdevices.QBlockdevFormatNode):
                            format_node.del_child_node(node)
                else:
                    self.remove(drive)
            self.remove(device, True)
            if ver_out is True:
                self.set_clean()
            elif out is False:
                raise DeviceUnplugError(device, "Device wasn't unplugged in "
                                        "qemu, but it was unplugged in device "
                                        "representation.", self)
        except (DeviceError, KeyError) as exc:
            device.unplug_unhook()
            raise DeviceUnplugError(device, exc, self)

        return out, ver_out

    def hotplug_verified(self):
        """
        This function should be used after you verify, that hotplug was
        successful. For each hotplug call, hotplug_verified have to be
        executed in order to mark VM as clear.

        :warning: If you can't verify, that hotplug was successful, don't
                  use this function! You could screw-up following tests.
        """
        self.set_clean()

    def list_missing_named_buses(self, bus_pattern, bus_type, bus_count):
        """
        :param bus_pattern: Bus name pattern with 1x%s for idx or %s is
                            appended in the end. ('mybuses' or 'my%sbus').
        :param bus_type: Type of the bus.
        :param bus_count: Desired number of buses.
        :return: List of buses, which are missing in range(bus_count)
        """
        if "%s" not in bus_pattern:
            bus_pattern = bus_pattern + "%s"
        missing_buses = [bus_pattern % i for i in xrange(bus_count)]
        for bus in self.__buses:
            if bus.type == bus_type and re.match(bus_pattern % '\d+',
                                                 bus.busid):
                if bus.busid in missing_buses:
                    missing_buses.remove(bus.busid)
        return missing_buses

    def idx_of_next_named_bus(self, bus_pattern):
        """
        :param bus_pattern: Bus name prefix without %s and tailing digit
        :return: Name of the next bus (integer is appended and incremented
                 until there is no existing bus).
        """
        if "%s" not in bus_pattern:
            bus_pattern = bus_pattern + "%s"
        buses = []
        for bus in self.__buses:
            if bus.busid and re.match(bus_pattern % '\d+', bus.busid):
                buses.append(bus.busid)
        i = 0
        while True:
            if bus_pattern % i not in buses:
                return i
            i += 1

    def cleanup_daemons(self):
        """Clean up daemons."""
        for dev in self:
            if isinstance(dev, qdevices.QVirtioFSDev):
                dev.clear()

    def cmdline(self, dynamic=True):
        """
        Creates cmdline arguments for creating all defined devices
        :return: cmdline of all devices (without qemu-cmd itself)
        """
        out = ""
        for device in self.__devices:
            if dynamic:
                _out = device.cmdline()
            else:
                _out = device.cmdline_nd()
            if _out:
                out += " %s" % _out
        if out:
            return out[1:]

    def hook_fill_scsi_hbas(self, params):
        """
        This hook creates dummy scsi hba per 7 -drive 'scsi' devices.
        """
        i = 6   # We are going to divide it by 7 so 6 will result in 0
        for image_name in params.objects("images"):
            image_params = params.object_params(image_name)
            _is_oldscsi = (image_params.get('drive_format') == 'scsi')
            _scsi_without_device = (not self.has_option('device') and
                                    params.object_params(image_name)
                                    .get('drive_format', 'virtio_blk')
                                    .startswith('scsi'))
            if _is_oldscsi or _scsi_without_device:
                i += 1

        for image_name in params.objects("cdroms"):
            _is_oldscsi = (params.object_params(image_name).get('cd_format') ==
                           'scsi')
            _scsi_without_device = (not self.has_option('device') and
                                    params.object_params(image_name)
                                    .get('cd_format', 'virtio_blk')
                                    .startswith('scsi'))
            if _is_oldscsi or _scsi_without_device:
                i += 1

        for i in xrange(i // 7):     # Autocreated lsi hba
            if arch.ARCH in ('ppc64', 'ppc64le'):
                _name = 'spapr-vscsi%s' % i
                bus = qdevices.QSCSIBus("scsi.0", 'SCSI', [64, 32],
                                        atype='spapr-vscsi')
                self.insert(qdevices.QStringDevice(_name,
                                                   child_bus=bus))
            else:
                _name = 'lsi53c895a%s' % i
                bus = qdevices.QSCSIBus(
                    "scsi.0", 'SCSI', [
                        8, 16384], atype='lsi53c895a')
                self.insert(qdevices.QStringDevice(_name,
                                                   parent_bus={'aobject':
                                                               params.get('pci_bus',
                                                                          'pci.0')},
                                                   child_bus=bus))

    # Machine related methods
    def machine_by_params(self, params=None):
        """
        Choose the used machine and set the default devices accordingly
        :param params: VM params
        :return: List of added devices (including default buses)
        """
        if self.has_device("pcie-root-port"):
            root_port_type = "pcie-root-port"
        else:
            root_port_type = "ioh3420"

        if self.has_device('pcie-pci-bridge'):
            pci_bridge_type = 'pcie-pci-bridge'
        else:
            pci_bridge_type = 'pci-bridge'

        def machine_q35(cmd=False):
            """
            Q35 + ICH9
            :param cmd: If set uses "-M $cmd" to force this machine type
            :return: List of added devices (including default buses)
            """
            logging.warn('Using Q35 machine which is not yet fully tested on '
                         'avocado-vt. False errors might occur.')
            devices = []
            bus = (qdevices.QPCIEBus('pcie.0', 'PCIE', root_port_type, 'pci.0'),
                   qdevices.QStrictCustomBus(None, [['chassis'], [256]], '_PCI_CHASSIS',
                                             first_port=[1]),
                   qdevices.QStrictCustomBus(None, [['chassis_nr'], [256]],
                                             '_PCI_CHASSIS_NR', first_port=[1]),
                   qdevices.QCPUBus(params.get("cpu_model"), [[""], [0]],
                                    "vcpu"))
            devices.append(qdevices.QStringDevice('machine', cmdline=cmd,
                                                  child_bus=bus,
                                                  aobject="pci.0"))
            devices.append(qdevices.QStringDevice('mch', {'addr': 0, 'driver': 'mch'},
                                                  parent_bus={'aobject': 'pci.0'}))
            devices.append(qdevices.QStringDevice('ICH9-LPC', {'addr': '1f.0',
                                                               'driver': 'ICH9-LPC'},
                                                  parent_bus={'aobject': 'pci.0'}))
            devices.append(qdevices.QStringDevice('ICH9 SMB', {'addr': '1f.3',
                                                               'driver': 'ICH9 SMB'},
                                                  parent_bus={'aobject': 'pci.0'}))
            devices.append(qdevices.QStringDevice('ICH9-ahci', {'addr': '1f.2',
                                                                'driver': 'ich9-ahci'},
                                                  parent_bus={
                                                      'aobject': 'pci.0'},
                                                  child_bus=qdevices.QAHCIBus('ide')))
            if self.has_option('device') and self.has_option("global"):
                devices.append(qdevices.QStringDevice('fdc',
                                                      child_bus=qdevices.QFloppyBus('floppy')))
            else:
                devices.append(qdevices.QStringDevice('fdc',
                                                      child_bus=qdevices.QOldFloppyBus('floppy'))
                               )

            # add default pcie root port plugging pcie device
            port_name = '%s-0' % root_port_type
            port_params = {
                'type': root_port_type,
                # reserve slot 0x0 for plugging in  pci bridge
                'reserved_slots': '0x0'}
            root_port = self.pcic_by_params(port_name, port_params)
            if root_port_type == 'pcie-root-port':
                root_port.set_param('multifunction', 'on')
            devices.append(root_port)

            # add pci bridge for plugging in legace pci device
            bridge_name = '%s-0' % pci_bridge_type
            bridge_parent_bus = {'aobject': root_port.get_qid()}
            bridge_params = {'type': pci_bridge_type}
            pci_bridge = self.pcic_by_params(bridge_name,
                                             bridge_params,
                                             bridge_parent_bus)
            pci_bridge.set_param('addr', '0x0')
            devices.append(pci_bridge)

            return devices

        def machine_i440FX(cmd=False):
            """
            i440FX + PIIX
            :param cmd: If set uses "-M $cmd" to force this machine type
            :return: List of added devices (including default buses)
            """
            devices = []
            pci_bus = "pci.0"
            bus = (qdevices.QPCIBus(pci_bus, 'PCI', 'pci.0'),
                   qdevices.QStrictCustomBus(None, [['chassis'], [256]], '_PCI_CHASSIS',
                                             first_port=[1]),
                   qdevices.QStrictCustomBus(None, [['chassis_nr'], [256]],
                                             '_PCI_CHASSIS_NR', first_port=[1]),
                   qdevices.QCPUBus(params.get("cpu_model"), [[""], [0]],
                                    "vcpu"))
            devices.append(qdevices.QStringDevice('machine', cmdline=cmd,
                                                  child_bus=bus,
                                                  aobject="pci.0"))
            devices.append(qdevices.QStringDevice('i440FX',
                                                  {'addr': 0, 'driver': 'i440FX'},
                                                  parent_bus={'aobject': 'pci.0'}))
            devices.append(qdevices.QStringDevice('PIIX4_PM', {'addr': '01.3',
                                                               'driver': 'PIIX4_PM'},
                                                  parent_bus={'aobject': 'pci.0'}))
            devices.append(qdevices.QStringDevice('PIIX3',
                                                  {'addr': 1, 'driver': 'PIIX3'},
                                                  parent_bus={'aobject': 'pci.0'}))
            devices.append(qdevices.QStringDevice('piix3-ide', {'addr': '01.1',
                                                                'driver': 'piix3-ide'},
                                                  parent_bus={
                                                      'aobject': 'pci.0'},
                                                  child_bus=qdevices.QIDEBus('ide')))
            if self.has_option('device') and self.has_option("global"):
                devices.append(qdevices.QStringDevice('fdc',
                                                      child_bus=qdevices.QFloppyBus('floppy')))
            else:
                devices.append(qdevices.QStringDevice('fdc',
                                                      child_bus=qdevices.QOldFloppyBus('floppy'))
                               )
            return devices

        def machine_pseries(cmd=False):
            """
            Pseries, not full support yet.
            :param cmd: If set uses "-M $cmd" to force this machine type
            :return: List of added devices (including default buses)
            """
            # TODO: This one is copied from machine_i440FX, in order to
            #  distinguish it from the i440FX, its bus structure will be
            #  modified in the future.
            devices = []
            pci_bus = "pci.0"
            bus = (qdevices.QPCIBus(pci_bus, 'PCI', 'pci.0'),
                   qdevices.QStrictCustomBus(None, [['chassis'], [256]], '_PCI_CHASSIS',
                                             first_port=[1]),
                   qdevices.QStrictCustomBus(None, [['chassis_nr'], [256]],
                                             '_PCI_CHASSIS_NR', first_port=[1]),
                   qdevices.QCPUBus(params.get("cpu_model"), [[""], [0]],
                                    "vcpu"))
            devices.append(qdevices.QStringDevice('machine', cmdline=cmd,
                                                  child_bus=bus,
                                                  aobject="pci.0"))
            devices.append(qdevices.QStringDevice('i440FX',
                                                  {'addr': 0, 'driver': 'i440FX'},
                                                  parent_bus={'aobject': 'pci.0'}))
            devices.append(qdevices.QStringDevice('PIIX4_PM', {'addr': '01.3',
                                                               'driver': 'PIIX4_PM'},
                                                  parent_bus={'aobject': 'pci.0'}))
            devices.append(qdevices.QStringDevice('PIIX3',
                                                  {'addr': 1, 'driver': 'PIIX3'},
                                                  parent_bus={'aobject': 'pci.0'}))
            devices.append(qdevices.QStringDevice('piix3-ide', {'addr': '01.1',
                                                                'driver': 'piix3-ide'},
                                                  parent_bus={
                                                      'aobject': 'pci.0'},
                                                  child_bus=qdevices.QIDEBus('ide')))
            if self.has_option('device') and self.has_option("global"):
                devices.append(qdevices.QStringDevice('fdc',
                                                      child_bus=qdevices.QFloppyBus('floppy')))
            else:
                devices.append(qdevices.QStringDevice('fdc',
                                                      child_bus=qdevices.QOldFloppyBus('floppy'))
                               )
            return devices

        def machine_arm64_mmio(cmd=False):
            """
            aarch64 (arm64) doesn't support PCI bus, only MMIO transports.
            Also it requires pflash for EFI boot.
            :param cmd: If set uses "-M $cmd" to force this machine type
            :return: List of added devices (including default buses)
            """
            def get_aavmf_vars(params):
                """
                Naive implementation of obtaining the main (first) image name
                """
                try:
                    first_image = params.objects('images')[0]
                    name = params.object_params(first_image).get('image_name')
                    return os.path.join(data_dir.DATA_DIR,
                                        name + "_AAVMF_VARS.fd")
                except IndexError:
                    raise DeviceError("Unable to map main image name to "
                                      "AAVMF variables file.")
            logging.warn('Support for aarch64 is highly experimental!')
            devices = []
            # EFI pflash
            aavmf_code = ("-drive file=/usr/share/AAVMF/AAVMF_CODE.fd,"
                          "if=pflash,format=raw,unit=0,readonly=on")
            devices.append(qdevices.QStringDevice('AAVMF_CODE',
                                                  cmdline=aavmf_code))
            aavmf_vars = get_aavmf_vars(params)
            force_create = params.get("force_create_image_image1",
                                      params.get("force_create_image"))
            if (force_create == "yes" or not os.path.exists(aavmf_vars)):
                if force_create != "yes":
                    logging.warn("AAVMF variables file '%s' doesn't exist, "
                                 "recreating it from the template (this should"
                                 " only happen when you install the machine as"
                                 " there is no default boot in EFI!)",
                                 aavmf_vars)
                shutil.copy2('/usr/share/AAVMF/AAVMF_VARS.fd', aavmf_vars)
            aavmf_vars = ("-drive file=%s,if=pflash,format=raw,unit=1"
                          % aavmf_vars)
            devices.append(qdevices.QStringDevice('AAVMF_VARS',
                                                  cmdline=aavmf_vars))
            # Add virtio-bus
            # TODO: Currently this uses QNoAddrCustomBus and does not
            # set the device's properties. This means that the qemu qtree
            # and autotest's representations are completelly different and
            # can't be used.
            bus = qdevices.QNoAddrCustomBus('bus', [['addr'], [32]],
                                            'virtio-mmio-bus', 'virtio-bus',
                                            'virtio-mmio-bus')
            devices.append(qdevices.QStringDevice('machine', cmdline=cmd,
                                                  child_bus=bus,
                                                  aobject="virtio-mmio-bus"))
            return devices

        def machine_arm64_pci(cmd=False):
            """
            Experimental support for pci-based aarch64
            :param cmd: If set uses "-M $cmd" to force this machine type
            :return: List of added devices (including default buses)
            """
            def get_aavmf_vars(params):
                """
                Naive implementation of obtaining the main (first) image name
                """
                try:
                    first_image = params.objects('images')[0]
                    name = params.object_params(first_image).get('image_name')
                    return os.path.join(data_dir.DATA_DIR,
                                        name + "_AAVMF_VARS.fd")
                except IndexError:
                    raise DeviceError("Unable to map main image name to "
                                      "AAVMF variables file.")
            logging.warn('Support for aarch64 is highly experimental!')
            devices = []
            # EFI pflash
            aavmf_code = ("-drive file=/usr/share/AAVMF/AAVMF_CODE.fd,"
                          "if=pflash,format=raw,unit=0,readonly=on")
            devices.append(qdevices.QStringDevice('AAVMF_CODE',
                                                  cmdline=aavmf_code))
            aavmf_vars = get_aavmf_vars(params)
            force_create = params.get("force_create_image_image1",
                                      params.get("force_create_image"))
            if (force_create == "yes" or not os.path.exists(aavmf_vars)):
                if force_create != "yes":
                    logging.warn("AAVMF variables file '%s' doesn't exist, "
                                 "recreating it from the template (this should"
                                 " only happen when you install the machine as"
                                 " there is no default boot in EFI!)",
                                 aavmf_vars)
                shutil.copy2('/usr/share/AAVMF/AAVMF_VARS.fd', aavmf_vars)
            aavmf_vars = ("-drive file=%s,if=pflash,format=raw,unit=1"
                          % aavmf_vars)
            devices.append(qdevices.QStringDevice('AAVMF_VARS',
                                                  cmdline=aavmf_vars))

            bus = (qdevices.QPCIEBus('pcie.0', 'PCIE', root_port_type, 'pci.0'),
                   qdevices.QStrictCustomBus(None, [['chassis'], [256]],
                                             '_PCI_CHASSIS', first_port=[1]),
                   qdevices.QStrictCustomBus(None, [['chassis_nr'], [256]],
                                             '_PCI_CHASSIS_NR', first_port=[1]))
            devices.append(qdevices.QStringDevice('machine', cmdline=cmd,
                                                  child_bus=bus,
                                                  aobject="pci.0"))
            devices.append(qdevices.QStringDevice('gpex-root',
                                                  {'addr': 0, 'driver': 'gpex-root'},
                                                  parent_bus={'aobject': 'pci.0'}))

            # add default pcie root port plugging pcie device
            port_name = '%s-0' % root_port_type
            port_params = {
                'type': root_port_type,
                # reserve slot 0x0 for plugging in  pci bridge
                'reserved_slots': '0x0'}
            root_port = self.pcic_by_params(port_name, port_params)
            if root_port_type == 'pcie-root-port':
                root_port.set_param('multifunction', 'on')
            devices.append(root_port)

            # add pci bridge for plugging in legace pci device
            bridge_name = '%s-0' % pci_bridge_type
            bridge_parent_bus = {'aobject': root_port.get_qid()}
            bridge_params = {'type': pci_bridge_type}
            pci_bridge = self.pcic_by_params(bridge_name,
                                             bridge_params,
                                             bridge_parent_bus)
            pci_bridge.set_param('addr', '0x0')
            devices.append(pci_bridge)

            return devices

        def machine_s390_virtio(cmd=False):
            """
            s390x (s390) doesn't support PCI bus.
            :param cmd: If set uses "-M $cmd" to force this machine type
            :return: List of added devices (including default buses)
            """
            devices = []
            # Add virtio-bus
            # TODO: Currently this uses QNoAddrCustomBus and does not
            # set the device's properties. This means that the qemu qtree
            # and autotest's representations are completelly different and
            # can't be used.
            logging.warn('Support for s390x is highly experimental!')
            bus = (qdevices.QNoAddrCustomBus('bus', [['addr'], [64]],
                                             'virtio-blk-ccw', 'virtio-bus',
                                             'virtio-blk-ccw'),
                   qdevices.QCPUBus(params.get("cpu_model"), [[""], [0]],
                                    "vcpu"))
            devices.append(qdevices.QStringDevice('machine', cmdline=cmd,
                                                  child_bus=bus,
                                                  aobject="virtio-blk-ccw"))
            return devices

        def machine_riscv64_mmio(cmd=False):
            """
            riscv doesn't support PCI bus, only MMIO transports.
            :param cmd: If set uses "-M $cmd" to force this machine type
            :return: List of added devices (including default buses)
            """
            logging.warn("Support for riscv64 is highly experimental. See "
                         "https://avocado-vt.readthedocs.io"
                         "/en/latest/Experimental.html#riscv64 for "
                         "setup information.")
            devices = []
            # Add virtio-bus
            # TODO: Currently this uses QNoAddrCustomBus and does not
            # set the device's properties. This means that the qemu qtree
            # and autotest's representations are completelly different and
            # can't be used.
            bus = qdevices.QNoAddrCustomBus('bus', [['addr'], [32]],
                                            'virtio-mmio-bus', 'virtio-bus',
                                            'virtio-mmio-bus')
            devices.append(qdevices.QStringDevice('machine', cmdline=cmd,
                                                  child_bus=bus,
                                                  aobject="virtio-mmio-bus"))
            return devices

        def machine_other(cmd=False):
            """
            isapc or unknown machine type. This type doesn't add any default
            buses or devices, only sets the cmdline.
            :param cmd: If set uses "-M $cmd" to force this machine type
            :return: List of added devices (including default buses)
            """
            logging.warn('Machine type isa/unknown is not supported by '
                         'avocado-vt. False errors might occur')
            devices = []
            devices.append(qdevices.QStringDevice('machine', cmdline=cmd))
            return devices

        machine_type = params.get('machine_type')
        machine_type_extra_params = params.get('machine_type_extra_params')
        if machine_type:
            split_machine_type = machine_type.split(':', 1)
            if len(split_machine_type) == 1:
                avocado_machine = ''
            else:
                avocado_machine, machine_type = split_machine_type
            m_types = []
            for _ in self.__machine_types.splitlines()[1:]:
                m_types.append(_.split()[0])

            if machine_type in m_types:
                if (self.has_option('M') or self.has_option('machine')):
                    cmd = "-machine %s" % machine_type
                    if machine_type_extra_params:
                        cmd += ",%s" % machine_type_extra_params.strip(',')
                else:
                    cmd = ""
                if 'q35' in machine_type:   # Q35 + ICH9
                    devices = machine_q35(cmd)
                elif avocado_machine == 'arm64-pci':
                    devices = machine_arm64_pci(cmd)
                elif avocado_machine == 'arm64-mmio':
                    devices = machine_arm64_mmio(cmd)
                elif machine_type.startswith("s390"):
                    devices = machine_s390_virtio(cmd)
                elif machine_type.startswith("pseries"):
                    devices = machine_pseries(cmd)
                elif avocado_machine == 'riscv64-mmio':
                    devices = machine_riscv64_mmio(cmd)
                elif 'isapc' not in machine_type:   # i440FX
                    devices = machine_i440FX(cmd)
                else:   # isapc (or other)
                    devices = machine_other(cmd)
            elif params.get("invalid_machine_type", "no") == "yes":
                # For negative testing pretend the unsupported machine is
                # similar to i440fx one (1 PCI bus, ..)
                devices = machine_i440FX("-M %s" % machine_type)
            else:
                raise exceptions.TestSkipError("Unsupported machine type %s." %
                                               (machine_type))
        else:
            devices = None
            for _ in self.__machine_types.splitlines()[1:]:
                if 'default' in _:
                    if 'q35' in machine_type:   # Q35 + ICH9
                        devices = machine_q35(False)
                    elif 'isapc' not in machine_type:   # i440FX
                        devices = machine_i440FX(False)
                    else:   # isapc (or other)
                        logging.warn('Machine isa/unknown is not supported by '
                                     'avocado-vt. False errors might occur')
                        devices = machine_other(False)
            if not devices:
                logging.warn('Unable to find the default machine type, using '
                             'i440FX')
                devices = machine_i440FX(False)

        if params.get("vm_pci_hole64_fix"):
            if machine_type.startswith('pc'):
                devices.append(qdevices.QGlobal("i440FX-pcihost", "x-pci-hole64-fix", "off"))
            if machine_type.startswith('q35'):
                devices.append(qdevices.QGlobal("q35-pcihost", "x-pci-hole64-fix", "off"))

        # reserve pci.0 addresses
        pci_params = params.object_params('pci.0')
        reserved = pci_params.get('reserved_slots', '').split()
        if reserved:
            for bus in self.__buses:
                if bus.aobject == "pci.0":
                    for addr in reserved:
                        bus.reserve(hex(int(addr)))
                    break
        return devices

    # USB Controller related methods
    def usbc_by_variables(self, usb_id, usb_type, pci_bus, multifunction=False,
                          masterbus=None, firstport=None, freq=None,
                          max_ports=6, pci_addr=None):
        """
        Creates usb-controller devices by variables
        :param usb_id: Usb bus name
        :param usb_type: Usb bus type
        :param multifunction: Is the bus multifunction
        :param masterbus: Is this bus master?
        :param firstport: Offset of the first port
        :param freq: Bus frequency
        :param max_ports: How many ports this bus have [6]
        :param pci_addr: Desired PCI address
        :return: List of QDev devices
        """
        if not self.has_option("device"):
            # Okay, for the archaic qemu which has not device parameter,
            # just return a usb uhci controller.
            # If choose this kind of usb controller, it has no name/id,
            # and only can be created once, so give it a special name.
            usb = qdevices.QStringDevice("oldusb", cmdline="-usb",
                                         child_bus=qdevices.QUSBBus(2, 'usb.0', 'uhci', usb_id))
            return [usb]

        if not self.has_device(usb_type):
            raise exceptions.TestSkipError("usb controller %s not available"
                                           % usb_type)

        usb = qdevices.QDevice(usb_type, {}, usb_id, pci_bus,
                               qdevices.QUSBBus(max_ports, '%s.0' % usb_id, usb_type, usb_id))
        new_usbs = [usb]    # each usb dev might compound of multiple devs
        # TODO: Add 'bus' property (it was not in the original version)
        usb.set_param('id', usb_id)
        usb.set_param('masterbus', masterbus)
        usb.set_param('multifunction', multifunction)
        usb.set_param('firstport', firstport)
        usb.set_param('freq', freq)
        usb.set_param('addr', pci_addr)
        if usb_type == "ich9-usb-ehci1":
            usb.set_param('addr', '1d.7')
            usb.set_param('multifunction', 'on')
            if arch.ARCH in ('ppc64', 'ppc64le'):
                for i in xrange(2):
                    new_usbs.append(qdevices.QDevice('pci-ohci', {}, usb_id))
                    new_usbs[-1].parent_bus = pci_bus
                    new_usbs[-1].set_param('id', '%s.%d' % (usb_id, i))
                    new_usbs[-1].set_param('multifunction', 'on')
                    new_usbs[-1].set_param('masterbus', '%s.0' % usb_id)
                    # current qdevices doesn't support x.y addr. Plug only
                    # the 0th one into this representation.
                    new_usbs[-1].set_param('addr', '1d.%d' % (3 * i))
                    new_usbs[-1].set_param('firstport', 3 * i)
            else:
                for i in xrange(3):
                    new_usbs.append(
                        qdevices.QDevice('ich9-usb-uhci%d' % (i + 1), {},
                                         usb_id))
                    new_usbs[-1].parent_bus = pci_bus
                    new_usbs[-1].set_param('id', '%s.%d' % (usb_id, i))
                    new_usbs[-1].set_param('multifunction', 'on')
                    new_usbs[-1].set_param('masterbus', '%s.0' % usb_id)
                    # current qdevices doesn't support x.y addr. Plug only
                    # the 0th one into this representation.
                    new_usbs[-1].set_param('addr', '1d.%d' % (2 * i))
                    new_usbs[-1].set_param('firstport', 2 * i)
        return new_usbs

    def usbc_by_params(self, usb_name, params, pci_bus={"aobject": "pci.0"}):
        """
        Wrapper for creating usb bus from autotest usb params.
        :param usb_name: Name of the usb bus
        :param params: USB params (params.object_params(usb_name))
        :return: List of QDev devices
        """
        return self.usbc_by_variables(usb_name,
                                      params.get('usb_type'),
                                      pci_bus,
                                      params.get('multifunction'),
                                      params.get('masterbus'),
                                      params.get('firstport'),
                                      params.get('freq'),
                                      int(params.get('max_ports', 6)),
                                      params.get('pci_addr'))

    # USB Device related methods
    def usb_by_variables(self, usb_name, usb_type, controller_type, bus=None,
                         port=None, serial=None):
        """
        Creates usb-devices by variables.
        :param usb_name: usb name
        :param usb_type: usb type (usb-tablet, usb-serial, ...)
        :param controller_type: type of the controller (uhci, ehci, xhci, ...)
        :param bus: the bus name (my_bus.0, ...)
        :param port: port specification (4, 4.1.2, ...)
        :param serial: serial specification (1234, d1, ...)
        :return: QDev device
        """
        if not self.has_device(usb_type):
            raise exceptions.TestSkipError("usb device %s not available"
                                           % usb_type)
        if self.has_option('device'):
            device = qdevices.QDevice(usb_type, aobject=usb_name)
            device.set_param('id', 'usb-%s' % usb_name)
            device.set_param('bus', bus)
            device.set_param('port', port)
            device.set_param('serial', serial)
            device.parent_bus += ({'type': controller_type},)
        else:
            if "tablet" in usb_type:
                device = qdevices.QStringDevice('usb-%s' % usb_name,
                                                cmdline='-usbdevice %s' % usb_name)
            else:
                device = qdevices.QStringDevice('missing-usb-%s' % usb_name)
                logging.error("This qemu supports only tablet device; ignoring"
                              " %s", usb_name)
        return device

    def usb_by_params(self, usb_name, params):
        """
        Wrapper for creating usb devices from autotest params.
        :param usb_name: Name of the usb
        :param params: USB device's params
        :return: QDev device
        """
        return self.usb_by_variables(usb_name,
                                     params.get("usb_type"),
                                     params.get("usb_controller"),
                                     params.get("bus"),
                                     params.get("port"),
                                     params.get("usbdev_serial"))

    # Images (disk, cdrom, floppy) device related methods
    def images_define_by_variables(self, name, filename, pci_bus, index=None,
                                   fmt=None, cache=None, werror=None,
                                   rerror=None, serial=None, snapshot=None,
                                   boot=None, blkdebug=None, bus=None,
                                   unit=None, port=None, bootindex=None,
                                   removable=None, min_io_size=None,
                                   opt_io_size=None, physical_block_size=None,
                                   logical_block_size=None, readonly=None,
                                   scsiid=None, lun=None, aio=None,
                                   strict_mode=None, media=None, imgfmt=None,
                                   pci_addr=None, scsi_hba=None,
                                   iothread=None, blk_extra_params=None,
                                   scsi=None, drv_extra_params=None,
                                   num_queues=None, bus_extra_params=None,
                                   force_fmt=None, image_encryption=None,
                                   image_access=None):
        """
        Creates related devices by variables
        :note: To skip the argument use None, to disable it use False
        :note: Strictly bool options accept "yes", "on" and True ("no"...)
        :param name: Autotest name of this disk
        :param filename: Path to the disk file
        :param index: drive index (used for generating names)
        :param fmt: drive subsystem type (ide, scsi, virtio, usb2, ...)
        :param force_fmt: Force to use specific drive format
        :param cache: disk cache (none, writethrough, writeback)
        :param werror: What to do when write error occurs (stop, ...)
        :param rerror: What to do when read error occurs (stop, ...)
        :param serial: drive serial number ($string)
        :param snapshot: use snapshot? ($bool)
        :param boot: is bootable? ($bool)
        :param blkdebug: use blkdebug (None, blkdebug_filename)
        :param bus: 1st level of disk location (index of bus) ($int)
        :param unit: 2nd level of disk location (unit/scsiid/...) ($int)
        :param port: 3rd level of disk location (port/lun/...) ($int)
        :param bootindex: device boot priority ($int)
        :param removable: can the drive be removed? ($bool)
        :param min_io_size: Min allowed io size
        :param opt_io_size: Optimal io size
        :param physical_block_size: set physical_block_size ($int)
        :param logical_block_size: set logical_block_size ($int)
        :param readonly: set the drive readonly ($bool)
        :param scsiid: Deprecated 2nd level of disk location (&unit)
        :param lun: Deprecated 3rd level of disk location (&port)
        :param aio: set the type of async IO (native, threads, ..)
        :param strict_mode: enforce optional parameters (address, ...) ($bool)
        :param media: type of the media (disk, cdrom, ...)
        :param imgfmt: image format (qcow2, raw, ...)
        :param pci_addr: drive pci address ($int)
        :param iothread: iothread specified
        :param scsi_hba: Custom scsi HBA
        :param num_queues: performace option for virtio-scsi-pci
        :param bus_extra_params: options want to add to virtio-scsi-pci bus
        :param image_encryption: ImageEncryption object for image
        :param image_access: The logical image access information object
        """
        def _get_access_tls_creds(image_access):
            """Get all tls-creds objects of the image and its backing images"""
            tls_creds = []
            if image_access is not None:
                creds_list = []
                if image_access.image_backing_auth:
                    creds_list.extend(image_access.image_backing_auth.values())
                if image_access.image_auth:
                    creds_list.append(image_access.image_auth)

                for creds in creds_list:
                    if creds.storage_type == 'nbd':
                        if creds.tls_creds:
                            tls_creds.append(creds)

            return tls_creds

        def _get_access_secrets(image_access):
            """Get all secret objects of the image and its backing images"""
            secrets = []
            if image_access is not None:
                access_info = []

                # backing images's access objects
                if image_access.image_backing_auth:
                    access_info.extend(image_access.image_backing_auth.values())

                # image's access object
                if image_access.image_auth is not None:
                    access_info.append(image_access.image_auth)

                for access in access_info:
                    if access.storage_type == 'ceph':
                        # Now we use 'key-secret' for both -drive and -blockdev,
                        # but for -drive, 'password-secret' also works, add an
                        # option in cfg file to enable 'password-secret' in future
                        if access.data:
                            secrets.append((access, 'key'))
                    elif access.storage_type == 'iscsi-direct':
                        if Flags.BLOCKDEV in self.caps:
                            # -blockdev: only password-secret is supported
                            if access.data:
                                secrets.append((access, 'password'))
                        else:
                            # -drive: u/p included in the filename
                            pass
            return secrets

        def define_hbas(qtype, atype, bus, unit, port, qbus, pci_bus, iothread,
                        addr_spec=None, num_queues=None,
                        bus_extra_params=None):
            """
            Helper for creating HBAs of certain type.
            """
            devices = []
            # AHCI uses multiple ports, id is different
            if qbus == qdevices.QAHCIBus:
                _hba = 'ahci%s'
            else:
                _hba = atype.replace('-', '_') + '%s.0'  # HBA id
            _bus = bus
            if bus is None:
                bus = self.get_first_free_bus({'type': qtype, 'atype': atype},
                                              [unit, port])
                if bus is None:
                    bus = self.idx_of_next_named_bus(_hba)
                else:
                    bus = bus.busid
            if isinstance(bus, int):
                for bus_name in self.list_missing_named_buses(
                        _hba, qtype, bus + 1):
                    _bus_name = bus_name.rsplit('.')[0]
                    bus_params = {'id': _bus_name, 'driver': atype}
                    if num_queues is not None and int(num_queues) > 1:
                        bus_params['num_queues'] = num_queues
                    if bus_extra_params:
                        for extra_param in bus_extra_params.split(","):
                            key, value = extra_param.split('=')
                            bus_params[key] = value
                    if addr_spec:
                        dev = qdevices.QDevice(params=bus_params,
                                               parent_bus=pci_bus,
                                               child_bus=qbus(busid=bus_name,
                                                              bus_type=qtype,
                                                              addr_spec=addr_spec,
                                                              atype=atype))
                    else:
                        dev = qdevices.QDevice(params=bus_params,
                                               parent_bus=pci_bus,
                                               child_bus=qbus(busid=bus_name))
                    if iothread:
                        try:
                            _iothread = self.allocate_iothread(iothread, dev)
                        except TypeError:
                            pass
                        else:
                            if _iothread and _iothread not in self:
                                devices.append(_iothread)
                    devices.append(dev)
                bus = _hba % bus
            if qbus == qdevices.QAHCIBus and unit is not None:
                bus += ".%d" % unit
            # If bus was not set, don't set it, unless the device is
            # a spapr-vscsi device.
            elif _bus is None and 'spapr_vscsi' not in _hba:
                bus = None
            return devices, bus, {'type': qtype, 'atype': atype}

        #
        # Parse params
        #
        devices = []    # All related devices

        # add required secret objects for image
        secret_obj = None
        if image_encryption:
            for secret in image_encryption.image_key_secrets:
                devices.append(qdevices.QObject("secret"))
                devices[-1].set_param("id", secret.aid)
                devices[-1].set_param("data", secret.data)
            if image_encryption.key_secret:
                secret_obj = devices[-1]

        access_secret_obj = None
        access_secret, secret_type = None, None
        image_secrets = _get_access_secrets(image_access)
        for sec, sectype in image_secrets:
            # create and add all secret objects: -object secret
            devices.append(qdevices.QObject('secret'))
            devices[-1].set_param("id", sec.aid)
            devices[-1].set_param('format', sec.data_format)

            if sectype == 'password':
                devices[-1].set_param("file", sec.filename)
            elif sectype == 'key':
                devices[-1].set_param("data", sec.data)

            if sec.image == name:
                # only the top image should be associated
                # with its secure object
                access_secret_obj = devices[-1]
                access_secret, secret_type = sec, sectype

        tls_creds = None
        tls_creds_obj = None
        creds_list = _get_access_tls_creds(image_access)
        for creds in creds_list:
            # create and add all tls-creds objects
            devices.append(qdevices.QObject('tls-creds-x509'))
            devices[-1].set_param("id", creds.aid)
            devices[-1].set_param("endpoint", 'client')
            devices[-1].set_param("dir", creds.tls_creds)

            if creds.image == name:
                # only the top image should be associated
                # with its tls-creds object
                tls_creds_obj = devices[-1]
                tls_creds = creds

        iscsi_initiator = None
        gluster_debug = None
        gluster_logfile = None
        gluster_peers = {}
        reconnect_delay = None
        access = image_access.image_auth if image_access else None
        if access is not None:
            if access.storage_type == 'iscsi-direct':
                iscsi_initiator = access.iscsi_initiator
            elif access.storage_type == 'glusterfs-direct':
                gluster_debug = access.debug
                gluster_logfile = access.logfile

                peers = []
                for peer in access.peers:
                    if 'path' in peer:
                        # access storage by unix domain socket
                        peers.append({'type': 'unix', 'path': peer['path']})
                    else:
                        # access storage by hostname/ip + port
                        peers.append({'host': peer['host'],
                                      'type': peer.get('type', 'inet'),
                                      'port': '%s' % peer.get('port', '0')})
                gluster_peers.update({'server.{i}.{k}'.format(i=i+1, k=k): v
                                     for i, server in enumerate(peers)
                                     for k, v in six.iteritems(server)})
            elif access.storage_type == 'nbd':
                reconnect_delay = access.reconnect_delay

        use_device = self.has_option("device")
        if fmt == "scsi":   # fmt=scsi force the old version of devices
            logging.warn("'scsi' drive_format is deprecated, please use the "
                         "new lsi_scsi type for disk %s", name)
            use_device = False
        if not fmt:
            use_device = False
        if fmt == 'floppy' and not self.has_option("global"):
            use_device = False

        if strict_mode is None:
            strict_mode = self.strict_mode
        if strict_mode:     # Force default variables
            if cache is None:
                cache = "none"
            if removable is None:
                removable = "yes"
            if aio is None:
                aio = "native"
            if media is None:
                media = "disk"
        else:       # Skip default variables
            if media != 'cdrom':    # ignore only 'disk'
                media = None

        if "[,boot=on|off]" not in self.get_help_text():
            if boot in ('yes', 'on', True):
                bootindex = "1"
            boot = None

        bus = none_or_int(bus)     # First level
        unit = none_or_int(unit)   # Second level
        port = none_or_int(port)   # Third level
        # Compatibility with old params - scsiid, lun
        if scsiid is not None:
            logging.warn("drive_scsiid param is obsolete, use drive_unit "
                         "instead (disk %s)", name)
            unit = none_or_int(scsiid)
        if lun is not None:
            logging.warn("drive_lun param is obsolete, use drive_port instead "
                         "(disk %s)", name)
            port = none_or_int(lun)
        if pci_addr is not None and fmt == 'virtio':
            logging.warn("drive_pci_addr is obsolete, use drive_bus instead "
                         "(disk %s)", name)
            bus = none_or_int(pci_addr)

        #
        # HBA
        # fmt: ide, scsi, virtio, scsi-hd, ahci, usb1,2,3 + hba
        # device: ide-drive, usb-storage, scsi-hd, scsi-cd, virtio-blk-pci
        # bus: ahci, virtio-scsi-pci, USB
        #
        if not use_device:
            if fmt and (fmt == "scsi" or (fmt.startswith('scsi')
                                          and (scsi_hba == 'lsi53c895a'
                                               or scsi_hba == 'spapr-vscsi'))):
                if not (bus is None and unit is None and port is None):
                    logging.warn("Using scsi interface without -device "
                                 "support; ignoring bus/unit/port. (%s)", name)
                    bus, unit, port = None, None, None
                # In case we hotplug, lsi wasn't added during the startup hook
                if arch.ARCH in ('ppc64', 'ppc64le'):
                    _ = define_hbas('SCSI', 'spapr-vscsi', None, None, None,
                                    qdevices.QSCSIBus, None, iothread,
                                    addr_spec=[64, 32])
                else:
                    _ = define_hbas('SCSI', 'lsi53c895a', None, None, None,
                                    qdevices.QSCSIBus, pci_bus, iothread,
                                    addr_spec=[8, 16384])
                devices.extend(_[0])
        elif fmt == "ide":
            if bus:
                logging.warn('ide supports only 1 hba, use drive_unit to set'
                             'ide.* for disk %s', name)
            bus = unit
            dev_parent = {'type': 'IDE', 'atype': 'ide'}
        elif fmt == "ahci":
            devs, bus, dev_parent = define_hbas('IDE', 'ahci', bus, unit, port,
                                                qdevices.QAHCIBus, pci_bus,
                                                iothread)
            devices.extend(devs)
        elif fmt.startswith('scsi-'):
            if not scsi_hba:
                scsi_hba = "virtio-scsi-pci"
            if scsi_hba != "virtio-scsi-pci":
                num_queues = None
            addr_spec = None
            if scsi_hba == 'lsi53c895a':
                addr_spec = [8, 16384]
            elif scsi_hba.startswith("virtio"):
                addr_spec = [256, 16384]
                if scsi_hba == 'virtio-scsi-device':
                    pci_bus = {'type': 'virtio-bus'}
                elif scsi_hba == 'virtio-scsi-ccw':
                    pci_bus = None
            elif scsi_hba == 'spapr-vscsi':
                addr_spec = [64, 32]
                pci_bus = None
            _, bus, dev_parent = define_hbas('SCSI', scsi_hba, bus, unit, port,
                                             qdevices.QSCSIBus, pci_bus,
                                             iothread, addr_spec,
                                             num_queues=num_queues,
                                             bus_extra_params=bus_extra_params)
            devices.extend(_)
        elif fmt in ('usb1', 'usb2', 'usb3'):
            if bus:
                logging.warn('Manual setting of drive_bus is not yet supported'
                             ' for usb disk %s', name)
                bus = None
            if fmt == 'usb1':
                dev_parent = {'type': 'uhci'}
            elif fmt == 'usb2':
                dev_parent = {'type': 'ehci'}
            elif fmt == 'usb3':
                dev_parent = {'type': 'xhci'}
        elif fmt == 'virtio':
            dev_parent = pci_bus
        elif fmt == 'virtio-blk-device':
            dev_parent = {'type': 'virtio-bus'}
        elif fmt == 'virtio-blk-ccw':   # For IBM s390 platform
            dev_parent = {'type': 'virtio-bus'}
        else:
            dev_parent = {'type': fmt}

        #
        # Drive mode:
        # -drive fmt or -drive fmt=none -device ...
        # Blockdev mode:
        # -blockdev node-name ... -device ...
        #
        if Flags.BLOCKDEV in self.caps:
            protocol_cls = qdevices.QBlockdevProtocolFile
            if not filename:
                protocol_cls = qdevices.QBlockdevProtocolNullCo
            elif filename.startswith('iscsi:'):
                protocol_cls = qdevices.QBlockdevProtocolISCSI
            elif filename.startswith('rbd:'):
                protocol_cls = qdevices.QBlockdevProtocolRBD
            elif filename.startswith('gluster'):
                protocol_cls = qdevices.QBlockdevProtocolGluster
            elif re.match(r'nbd(\+\w+)?://', filename):
                protocol_cls = qdevices.QBlockdevProtocolNBD
            elif filename.startswith('nvme:'):
                protocol_cls = qdevices.QBlockdevProtocolNVMe
            elif fmt in ('scsi-generic', 'scsi-block'):
                protocol_cls = qdevices.QBlockdevProtocolHostDevice
            elif blkdebug is not None:
                protocol_cls = qdevices.QBlockdevProtocolBlkdebug

            if imgfmt == 'qcow2':
                format_cls = qdevices.QBlockdevFormatQcow2
            elif imgfmt == 'raw' or media == 'cdrom':
                format_cls = qdevices.QBlockdevFormatRaw
            elif imgfmt == 'luks':
                format_cls = qdevices.QBlockdevFormatLuks
            elif imgfmt == 'nvme':
                format_cls = qdevices.QBlockdevFormatRaw
            elif imgfmt is None:
                # use RAW type as the default
                format_cls = qdevices.QBlockdevFormatRaw

            format_node = format_cls(name)
            protocol_node = protocol_cls(name)
            format_node.add_child_node(protocol_node)
            devices.append(protocol_node)
            devices.append(format_node)
        else:
            if self.has_hmp_cmd('__com.redhat_drive_add') and use_device:
                devices.append(qdevices.QRHDrive(name))
            elif self.has_hmp_cmd('drive_add') and use_device:
                devices.append(qdevices.QHPDrive(name))
            elif self.has_option("device"):
                devices.append(qdevices.QDrive(name, use_device))
            else:       # very old qemu without 'addr' support
                devices.append(qdevices.QOldDrive(name, use_device))

        if Flags.BLOCKDEV in self.caps:
            for opt, val in zip(('serial', 'boot'), (serial, boot)):
                if val is not None:
                    logging.warn("The command line option %s is not supported "
                                 "on %s by -blockdev." % (opt, name))
            if media == 'cdrom':
                readonly = 'on'
            devices[-2].set_param('read-only', readonly, bool)
            devices[-1].set_param('read-only', readonly, bool)
            if secret_obj:
                if isinstance(devices[-1], qdevices.QBlockdevFormatQcow2):
                    devices[-1].set_param('encrypt.format',
                                          image_encryption.format)
                    devices[-1].set_param('encrypt.key-secret',
                                          secret_obj.get_qid())
                elif isinstance(devices[-1], qdevices.QBlockdevFormatLuks):
                    devices[-1].set_param('key-secret', secret_obj.get_qid())
        else:
            devices[-1].set_param('if', 'none')
            devices[-1].set_param('rerror', rerror)
            devices[-1].set_param('werror', werror)
            devices[-1].set_param('serial', serial)
            devices[-1].set_param('boot', boot, bool)
            devices[-1].set_param('snapshot', snapshot, bool)
            devices[-1].set_param('readonly', readonly, bool)
            if secret_obj:
                if imgfmt == "qcow2":
                    devices[-1].set_param('encrypt.format',
                                          image_encryption.format)
                    devices[-1].set_param('encrypt.key-secret',
                                          secret_obj.get_qid())
                elif imgfmt == "luks":
                    devices[-1].set_param('key-secret', secret_obj.get_qid())

        if 'aio' in self.get_help_text():
            if aio == 'native' and snapshot == 'yes':
                logging.warn('snapshot is on, fallback aio to threads.')
                aio = 'threads'
            if Flags.BLOCKDEV in self.caps:
                if isinstance(devices[-2], (qdevices.QBlockdevProtocolFile,
                                            qdevices.QBlockdevProtocolHostDevice,
                                            qdevices.QBlockdevProtocolHostCdrom)):
                    devices[-2].set_param('aio', aio)
            else:
                devices[-1].set_param('aio', aio)
            if aio == 'native':
                # Since qemu 2.6, aio=native has no effect without
                # cache.direct=on or cache=none, It will be error out.
                # Please refer to qemu commit d657c0c.
                cache = cache not in ['none', 'directsync'] and 'none' or cache
        # Forbid to specify the cache mode for empty drives.
        # More info from qemu commit 91a097e74.
        if not filename:
            cache = None
        if filename.startswith('nvme://'):
            # NVMe controller doesn't support write cache configuration
            cache = 'writethrough'
        if Flags.BLOCKDEV in self.caps:
            if filename:
                file_opts = qemu_storage.filename_to_file_opts(filename)
                for key, value in six.iteritems(file_opts):
                    devices[-2].set_param(key, value)

            if access_secret is not None:
                if secret_type == 'password':
                    devices[-2].set_param('password-secret',
                                          access_secret_obj.get_qid())
                elif secret_type == 'key':
                    devices[-2].set_param('key-secret',
                                          access_secret_obj.get_qid())

            if tls_creds is not None:
                devices[-2].set_param('tls-creds', tls_creds_obj.get_qid())
            if reconnect_delay is not None:
                devices[-2].set_param('reconnect-delay', int(reconnect_delay))
            if iscsi_initiator:
                devices[-2].set_param('initiator-name', iscsi_initiator)
            if gluster_debug:
                devices[-2].set_param('debug', int(gluster_debug))
            if gluster_logfile:
                devices[-2].set_param('logfile', gluster_logfile)
            for key, value in six.iteritems(gluster_peers):
                devices[-2].set_param(key, value)

            for dev in (devices[-1], devices[-2]):
                if not cache:
                    direct, no_flush = (None, None)
                else:
                    direct, no_flush = (self.cache_map[cache]['cache.direct'],
                                        self.cache_map[cache]['cache.no-flush'])
                dev.set_param('cache.direct', direct)
                dev.set_param('cache.no-flush', no_flush)
            devices[-1].set_param('file', devices[-2].get_qid())
        else:
            devices[-1].set_param('cache', cache)
            devices[-1].set_param('media', media)
            devices[-1].set_param('format', imgfmt)
            if blkdebug is not None:
                devices[-1].set_param('file', 'blkdebug:%s:%s' % (blkdebug, filename))
            else:
                devices[-1].set_param('file', filename)

            if access_secret is not None:
                if secret_type == 'password':
                    devices[-1].set_param('file.password-secret',
                                          access_secret_obj.get_qid())
                elif secret_type == 'key':
                    devices[-1].set_param('file.key-secret',
                                          access_secret_obj.get_qid())

            if tls_creds is not None:
                devices[-1].set_param('file.tls-creds',
                                      tls_creds_obj.get_qid())
            if reconnect_delay is not None:
                devices[-1].set_param('file.reconnect-delay',
                                      int(reconnect_delay))
            if iscsi_initiator:
                devices[-1].set_param('file.initiator-name', iscsi_initiator)
            if gluster_debug:
                devices[-1].set_param('file.debug', int(gluster_debug))
            if gluster_logfile:
                devices[-1].set_param('file.logfile', gluster_logfile)

        if drv_extra_params:
            drv_extra_params = (_.split('=', 1) for _ in
                                drv_extra_params.split(',') if _)
            for key, value in drv_extra_params:
                if Flags.BLOCKDEV in self.caps:
                    if key == 'discard':
                        value = re.sub('on', 'unmap', re.sub('off', 'ignore', value))
                    if key == 'cache-size':
                        devices[-2].set_param(key, None)
                    else:
                        devices[-2].set_param(key, value)
                devices[-1].set_param(key, value)
        if not use_device:
            if fmt and fmt.startswith('scsi-'):
                if scsi_hba == 'lsi53c895a' or scsi_hba == 'spapr-vscsi':
                    fmt = 'scsi'  # Compatibility with the new scsi
            if fmt and fmt not in ('ide', 'scsi', 'sd', 'mtd', 'floppy',
                                   'pflash', 'virtio'):
                raise virt_vm.VMDeviceNotSupportedError(self.vmname,
                                                        fmt)
            devices[-1].set_param('if', fmt)    # overwrite previously set None
            if not fmt:     # When fmt unspecified qemu uses ide
                fmt = 'ide'
            devices[-1].set_param('index', index)
            if fmt == 'ide':
                devices[-1].parent_bus = ({'type': fmt.upper(), 'atype': fmt},)
            elif fmt == 'scsi':
                if arch.ARCH in ('ppc64', 'ppc64le'):
                    devices[-1].parent_bus = ({'atype': 'spapr-vscsi',
                                               'type': 'SCSI'},)
                else:
                    devices[-1].parent_bus = ({'atype': 'lsi53c895a',
                                               'type': 'SCSI'},)
            elif fmt == 'floppy':
                devices[-1].parent_bus = ({'type': fmt},)
            elif fmt == 'virtio':
                devices[-1].set_param('addr', pci_addr)
                devices[-1].parent_bus = (pci_bus,)
            if not media == 'cdrom':
                logging.warn("Using -drive fmt=xxx for %s is unsupported "
                             "method, false errors might occur.", name)
            return devices

        #
        # Device
        #
        devices.append(qdevices.QDevice(params={}, aobject=name))
        devices[-1].parent_bus += ({'busid': 'drive_%s' % name}, dev_parent)
        if fmt in ("ide", "ahci"):
            if not self.has_device('ide-hd'):
                devices[-1].set_param('driver', 'ide-drive')
            elif media == 'cdrom':
                devices[-1].set_param('driver', 'ide-cd')
            else:
                devices[-1].set_param('driver', 'ide-hd')
            devices[-1].set_param('unit', port)
        elif fmt and fmt.startswith('scsi-'):
            devices[-1].set_param('driver', fmt)
            devices[-1].set_param('scsi-id', unit)
            devices[-1].set_param('lun', port)
            devices[-1].set_param('removable', removable, bool)
            if strict_mode:
                devices[-1].set_param('channel', 0)
        elif fmt == 'virtio':
            devices[-1].set_param('driver', 'virtio-blk-pci')
            devices[-1].set_param("scsi", scsi, bool)
            if bus is not None:
                devices[-1].set_param('addr', hex(bus))
                bus = None
            if iothread:
                try:
                    iothread = self.allocate_iothread(iothread, devices[-1])
                except TypeError:
                    pass
                else:
                    if iothread and iothread not in self:
                        devices.insert(-2, iothread)
        elif fmt in ('usb1', 'usb2', 'usb3'):
            devices[-1].set_param('driver', 'usb-storage')
            devices[-1].set_param('port', unit)
            devices[-1].set_param('removable', removable, bool)
        elif fmt == 'floppy':
            # Overwrite qdevices.QDevice with qdevices.QFloppy
            devices[-1] = qdevices.QFloppy(unit, 'drive_%s' % name, name,
                                           ({'busid': 'drive_%s' % name}, {'type': fmt}))
        else:
            logging.warn('Using default device handling (disk %s)', name)
            devices[-1].set_param('driver', fmt)
        if force_fmt:
            logging.info("Force to use %s for the device" % force_fmt)
            devices[-1].set_param('driver', force_fmt)
        # Get the supported options
        options = self.execute_qemu("-device %s,?" % devices[-1]['driver'])
        devices[-1].set_param('id', name)
        devices[-1].set_param('bus', bus)
        devices[-1].set_param('drive', 'drive_%s' % name)
        devices[-1].set_param('logical_block_size', logical_block_size)
        devices[-1].set_param('physical_block_size', physical_block_size)
        devices[-1].set_param('min_io_size', min_io_size)
        devices[-1].set_param('opt_io_size', opt_io_size)
        devices[-1].set_param('bootindex', bootindex)
        if Flags.BLOCKDEV in self.caps:
            if isinstance(devices[-3], qdevices.QBlockdevProtocolHostDevice):
                self.cache_map[cache]['write-cache'] = None
            write_cache = None if not cache else self.cache_map[cache]['write-cache']
            devices[-1].set_param('write-cache', write_cache)
            if 'scsi-generic' == fmt:
                rerror, werror = (None, None)
            devices[-1].set_param('rerror', rerror)
            devices[-1].set_param('werror', werror)
        if 'serial' in options:
            devices[-1].set_param('serial', serial)
            devices[-2].set_param('serial', None)   # remove serial from drive
        if blk_extra_params:
            blk_extra_params = (_.split('=', 1) for _ in
                                blk_extra_params.split(',') if _)
            for key, value in blk_extra_params:
                devices[-1].set_param(key, value)
        return devices

    def images_define_by_params(self, name, image_params, media=None,
                                index=None, image_boot=None,
                                image_bootindex=None,
                                pci_bus={"aobject": "pci.0"}):
        """
        Wrapper for creating disks and related hbas from autotest image params.

        :note: To skip the argument use None, to disable it use False
        :note: Strictly bool options accept "yes", "on" and True ("no"...)
        :note: Options starting with '_' are optional and used only when
               strict_mode is True
        :param name: Name of the new disk
        :param params: Disk params (params.object_params(name))
        """
        data_root = data_dir.get_data_dir()
        shared_dir = os.path.join(data_root, "shared")
        drive_format = image_params.get("drive_format")
        scsi_hba = image_params.get("scsi_hba", "virtio-scsi-pci")
        if drive_format == "virtio":    # translate virtio to ccw/device
            machine_type = image_params.get("machine_type")
            if "s390" in machine_type:      # s390
                drive_format = "virtio-blk-ccw"
            elif "mmio" in machine_type:    # mmio-based machine
                drive_format = "virtio-blk-device"
        if scsi_hba == "virtio-scsi-pci":
            if "mmio" in image_params.get("machine_type"):
                scsi_hba = "virtio-scsi-device"
            elif "s390" in image_params.get("machine_type"):
                scsi_hba = "virtio-scsi-ccw"
        image_encryption = storage.ImageEncryption.encryption_define_by_params(
            name, image_params)

        # all access information for the logical image
        image_access = storage.ImageAccessInfo.access_info_define_by_params(
            name, image_params)

        image_filename = storage.get_image_filename(image_params, data_root)
        imgfmt = image_params.get("image_format")
        if (Flags.BLOCKDEV in self.caps and
                image_params.get("image_snapshot") == "yes"):
            sn_params = Params()
            for k, v in image_params.items():
                sn_params['%s_%s' % (k, name)] = v
            sn = 'vl_%s_%s' % (self.vmname, name)
            sn_params['image_chain'] = "%s %s" % (name, sn)
            sn_params['image_name'] = sn
            sn_params['image_size'] = image_params['image_size']
            sn_img = qemu_storage.QemuImg(sn_params, data_dir.get_data_dir(), sn)
            image_filename = sn_img.create(sn_params)[0]
            os.chmod(image_filename, stat.S_IRUSR | stat.S_IWUSR)
            logging.info(
                "'snapshot=on' is not supported by '-blockdev' but "
                "requested from the image '%s', imitating the behavior "
                "of '-drive' to keep compatibility", name)
            self.temporary_image_snapshots.add(image_filename)
            image_encryption = storage.ImageEncryption.encryption_define_by_params(
                sn, sn_params)
            imgfmt = 'qcow2'

        return self.images_define_by_variables(name,
                                               image_filename,
                                               pci_bus,
                                               index,
                                               drive_format,
                                               image_params.get("drive_cache"),
                                               image_params.get(
                                                   "drive_werror"),
                                               image_params.get(
                                                   "drive_rerror"),
                                               image_params.get(
                                                   "drive_serial"),
                                               image_params.get(
                                                   "image_snapshot"),
                                               image_boot,
                                               storage.get_image_blkdebug_filename(
                                                   image_params,
                                                   shared_dir),
                                               image_params.get("drive_bus"),
                                               image_params.get("drive_unit"),
                                               image_params.get("drive_port"),
                                               image_bootindex,
                                               image_params.get("removable"),
                                               image_params.get("min_io_size"),
                                               image_params.get("opt_io_size"),
                                               image_params.get(
                                                   "physical_block_size"),
                                               image_params.get(
                                                   "logical_block_size"),
                                               image_params.get(
                                                   "image_readonly"),
                                               image_params.get(
                                                   "drive_scsiid"),
                                               image_params.get("drive_lun"),
                                               image_params.get("image_aio"),
                                               image_params.get(
                                                   "strict_mode") == "yes",
                                               media,
                                               imgfmt,
                                               image_params.get(
                                                   "drive_pci_addr"),
                                               scsi_hba,
                                               image_params.get(
                                                   "image_iothread"),
                                               image_params.get(
                                                   "blk_extra_params"),
                                               image_params.get(
                                                   "virtio-blk-pci_scsi"),
                                               image_params.get(
                                                   "drv_extra_params"),
                                               image_params.get("num_queues"),
                                               image_params.get(
                                                   "bus_extra_params"),
                                               image_params.get(
                                                   "force_drive_format"),
                                               image_encryption,
                                               image_access)

    def serials_define_by_variables(self, serial_id, serial_type, chardev_id,
                                    bus_type=None, serial_name=None,
                                    bus=None, nr=None, reg=None,
                                    bus_extra_params=''):
        """
        Creates related devices by variables

        :param serial_id: the id of the serial device
        :param serial_type: the type of the serial device
        :param chardev_id: the id of the chardev device
        :param bus_type: bus type of the serial device(optional, virtio only)
        :param serial_name: the name option of serial device(optional)
        :param bus: the busid of parent bus(optional, virtio only) or
               a parameter '<new>' which means one new parent bus
        :param nr: the nr(port) of the parent bus(optional, virtio only)
        :param reg: reg option of isa-serial(optional)
        :param bus_extra_params: extra virtio_serial_pci params
        :return: the device list that construct the serial device
        """

        devices = []
        bus_params = (dict([_.split('=')
                            for _ in bus_extra_params.split(',') if _]))
        # For virtio devices, generate controller and create the port device
        if serial_type.startswith('virt'):
            if not bus or bus == '<new>':
                if bus_type == 'virtio-serial-device':
                    pci_bus = {'type': 'virtio-bus'}
                else:
                    pci_bus = {'aobject': 'pci.0'}
                if bus != '<new>':
                    bus = self.get_first_free_bus(
                        {'type': 'SERIAL', 'atype': bus_type}, [None, nr])
                #  Multiple virtio console devices can't share a single bus
                if bus is None or bus == '<new>' or \
                        serial_type == 'virtconsole':
                    _hba = bus_type.replace('-', '_') + '%s'
                    bus = self.idx_of_next_named_bus(_hba)
                    bus = self.list_missing_named_buses(
                        _hba, 'SERIAL', bus + 1)[-1]
                    logging.debug("list missing named bus: %s", bus)
                    bus_params["id"] = bus
                    devices.append(
                        qdevices.QDevice(bus_type,
                                         bus_params,
                                         bus,
                                         pci_bus,
                                         qdevices.QSerialBus(
                                             bus, bus_type, bus)))
                else:
                    bus = bus.busid
            devices.append(
                qdevices.QDevice(serial_type,
                                 {"id": serial_id},
                                 parent_bus={'busid': bus}))
            devices[-1].set_param('name', serial_name)
        elif serial_type.startswith('pci'):
            # plug pci* serial device into pci bus
            devices.append(qdevices.QDevice(serial_type,
                                            {"id": serial_id},
                                            parent_bus=bus))
        else:  # none virtio type, generate serial device directly
            devices.append(qdevices.QDevice(serial_type, {"id": serial_id}))
            devices[-1].set_param("reg", reg)
        devices[-1].set_param('chardev', chardev_id)

        return devices

    def serials_define_by_params(self, serial_id, params,
                                 file_name=None):
        """
        Wrapper for creating serial device from serial params.

        :param serial_id: id of serial object
        :param params: serial params
        :param file_name: the file path of the serial device (optional)
        :return: the device list that construct the serial device
        """
        serial_type = params['serial_type']
        machine = params.get('machine_type')

        # Arm lists "isa-serial" as supported but can't use it,
        # fallback to "-serial"
        legacy_cmd = " -serial unix:'%s',server,nowait" % file_name
        legacy_dev = qdevices.QStringDevice('SER-%s' % serial_id,
                                            cmdline=legacy_cmd)
        arm_serial = (serial_type == 'isa-serial'
                      and 'arm' in params.get("machine_type", ""))
        if (arm_serial or not self.has_option("chardev")
                or not self.has_device(serial_type)):
            return legacy_dev

        bus_type = None
        if serial_type.startswith('virt'):
            if '-mmio' in machine:
                controller_suffix = 'device'
            elif machine.startswith("s390"):
                controller_suffix = 'ccw'
            else:
                controller_suffix = 'pci'
            bus_type = 'virtio-serial-%s' % controller_suffix
        chardev_id = 'chardev_%s' % serial_id
        chardev_device = self.chardev_define_by_params(chardev_id, params, file_name)
        serial_devices = self.serials_define_by_variables(
            serial_id, serial_type, chardev_id, bus_type=bus_type,
            serial_name=params.get("serial_name"), bus=params.get("serial_bus"),
            nr=params.get("serial_nr"), reg=params.get("serial_reg"),
            bus_extra_params=params.get("virtio_serial_extra_params", ""))

        return [chardev_device] + serial_devices

    def chardev_define_by_params(self, chardev_id, params, file_name=None):
        """
        Wrapper for creating -chardev device from params.
        :param chardev_id: chardev id
        :param params: chardev params
        :param file_name: file name of chardev (optional)
        :return: CharDevice object
        """
        backend = params.get('chardev_backend', 'unix_socket')
        # for tcp_socket and unix_socket, both form to 'socket'
        _backend = 'socket' if 'socket' in backend else backend
        # Generate -chardev device
        chardev_param = Params({'backend': _backend, 'id': chardev_id})
        if backend in ['unix_socket', 'file', 'pipe', 'serial',
                       'tty', 'parallel', 'parport']:
            chardev_param.update({'path': file_name})
            if (backend == 'pipe' and params.get('auto_create_pipe', 'yes') == "yes"):
                process.system("mkfifo %s" % file_name)
        elif backend in ['udp', 'tcp_socket']:
            chardev_param.update(
                {'host': params['chardev_host'],
                 'port': params['chardev_port'],
                 'ipv4': params.get('chardev_ipv4'),
                 'ipv6': params.get('chardev_ipv6')})
        if backend == 'tcp_socket':
            chardev_param.update({'to': params.get('chardev_to')})
        if 'socket' in backend:  # tcp_socket & unix_socket
            chardev_param.update(
                {'server': params.get('chardev_server', 'yes'),
                 'nowait': params.get('chardev_nowait', 'yes')})
        elif backend in ['spicevmc', 'spiceport']:
            chardev_param.update(
                {'debug': params.get('chardev_debug'),
                 'name': params.get('chardev_name')})
        elif 'ringbuf' in backend:
            chardev_param.update(
                {'ringbuf_write_size': int(params.get('ringbuf_write_size'))})
        return qdevices.CharDevice(chardev_param, chardev_id)

    def cdroms_define_by_params(self, name, image_params, media=None,
                                index=None, image_boot=None,
                                image_bootindex=None,
                                pci_bus={"aobject": "pci.0"}):
        """
        Wrapper for creating cdrom and related hbas from autotest image params.

        :note: To skip the argument use None, to disable it use False
        :note: Strictly bool options accept "yes", "on" and True ("no"...)
        :note: Options starting with '_' are optional and used only when
               strict_mode is True
        :param name: Name of the new disk
        :param params: Disk params (params.object_params(name))
        """
        image_params["image_name"] = ""
        iso = image_params.get('cdrom')
        if iso:
            image_name = os.path.realpath(
                os.path.join(
                    data_dir.get_data_dir(),
                    image_params.get('cdrom')))
            image_params['image_name'] = image_name
        image_params['image_raw_device'] = 'yes'
        cd_format = image_params.get('cd_format')
        scsi_hba = image_params.get("scsi_hba")
        if cd_format in (None, "ide", "scsi-cd"):
            machine_type = image_params.get("machine_type")
            if machine_type == "pseries":
                cd_format = "scsi-cd"
            elif "mmio" in machine_type:
                cd_format = "scsi-cd"
                scsi_hba = "virtio-scsi-device"
            elif "pci" in machine_type:
                cd_format = "scsi-cd"
                scsi_hba = "virtio-scsi-pci"
            elif "s390" in machine_type:
                cd_format = "scsi-cd"
                scsi_hba = "virtio-scsi-ccw"
        if cd_format in (None, "ide"):
            if not self.get_buses({'atype': 'ide'}):
                logging.warn("cd_format IDE not available, using AHCI "
                             "instead.")
                cd_format = 'ahci'
        if scsi_hba == "virtio-scsi-pci":
            if "mmio" in image_params.get("machine_type"):
                scsi_hba = "virtio-scsi-device"
            elif "s390" in image_params.get("machine_type"):
                scsi_hba = "virtio-scsi-ccw"
        shared_dir = os.path.join(data_dir.get_data_dir(), "shared")
        cache_mode = image_params.get('image_aio') == 'native' and 'none' or ''
        return self.images_define_by_variables(name,
                                               storage.get_image_filename(
                                                   image_params,
                                                   data_dir.get_data_dir()),
                                               pci_bus,
                                               index,
                                               cd_format,
                                               image_params.get(
                                                   "drive_cache", cache_mode),
                                               image_params.get(
                                                   "drive_werror"),
                                               image_params.get(
                                                   "drive_rerror"),
                                               image_params.get(
                                                   "drive_serial"),
                                               image_params.get(
                                                   "image_snapshot"),
                                               image_boot,
                                               storage.get_image_blkdebug_filename(
                                                   image_params,
                                                   shared_dir),
                                               image_params.get("drive_bus"),
                                               image_params.get("drive_unit"),
                                               image_params.get("drive_port"),
                                               image_bootindex,
                                               image_params.get("removable"),
                                               image_params.get("min_io_size"),
                                               image_params.get("opt_io_size"),
                                               image_params.get(
                                                   "physical_block_size"),
                                               image_params.get(
                                                   "logical_block_size"),
                                               image_params.get(
                                                   "image_readonly"),
                                               image_params.get(
                                                   "drive_scsiid"),
                                               image_params.get("drive_lun"),
                                               image_params.get("image_aio"),
                                               image_params.get(
                                                   "strict_mode") == "yes",
                                               media,
                                               None,     # skip img_fmt
                                               image_params.get(
                                                   "drive_pci_addr"),
                                               scsi_hba,
                                               None,    # skip iothread
                                               image_params.get(
                                                   "blk_extra_params"),
                                               image_params.get(
                                                   "virtio-blk-pci_scsi"),
                                               image_params.get(
                                                   "drv_extra_params"),
                                               None,
                                               image_params.get(
                                                   "bus_extra_params"),
                                               image_params.get("force_drive_format"))

    def pcic_by_params(self, name, params, parent_bus=None):
        """
        Creates pci controller/switch/... based on params

        :param name: Autotest name
        :param params: PCI controller params
        :note: x3130 creates x3130-upstream bus + xio3130-downstream port for
               each inserted device.
        :warning: x3130-upstream device creates only x3130-upstream device
                  and you are responsible for creating the downstream ports.
        """
        driver = params.get('type', 'pcie-root-port')
        pcic_params = {"id": name}
        if driver in ('pcie-root-port', 'ioh3420', 'x3130-upstream', 'x3130'):
            bus_type = 'PCIE'
        else:
            bus_type = 'PCI'
        if not parent_bus:
            parent_bus = [{'aobject': params.get('pci_bus', 'pci.0')}]
        elif not isinstance(parent_bus, (list, tuple)):
            parent_bus = [parent_bus]
        if driver == 'x3130':
            bus = qdevices.QPCISwitchBus(
                name, bus_type, 'xio3130-downstream', name)
            driver = 'x3130-upstream'
        else:
            if driver == 'pci-bridge':  # addr 0x01-0x1f, chasis_nr
                parent_bus.append({'busid': '_PCI_CHASSIS_NR'})
                bus_length = 32
                bus_first_port = 1
            elif driver == 'i82801b11-bridge':  # addr 0x1-0x13
                bus_length = 20
                bus_first_port = 1
            elif driver in ('pcie-root-port', 'ioh3420'):
                bus_length = 1
                bus_first_port = 0
                parent_bus.append({'busid': '_PCI_CHASSIS'})
            elif driver == 'pcie-pci-bridge':
                params['reserved_slots'] = '0x0'
                # Unsupported PCI slot 0 for standard hotplug controller.
                # Valid slots are between 1 and 31
                bus_length = 32
                bus_first_port = 1
            else:   # addr = 0x0-0x1f
                bus_length = 32
                bus_first_port = 0
            bus = qdevices.QPCIBus(
                name, bus_type, name, bus_length, bus_first_port)
        for addr in params.get('reserved_slots', '').split():
            bus.reserve(addr)
        return qdevices.QDevice(driver, pcic_params, aobject=name,
                                parent_bus=parent_bus,
                                child_bus=bus)

    def memory_object_define_by_params(self, params, name):
        """
        Create memory object from params, default backend type is
        'memory-backend-ram'.
        """
        params = params.object_params("mem")
        attrs = qdevices.Memory.__attributes__[:]
        params = params.copy_from_keys(attrs)
        params.setdefault("backend", "memory-backend-ram")
        dev = qdevices.Memory(params["backend"], params)
        dev.set_param("id", "%s-%s" % ("mem", name))
        return dev

    def dimm_device_define_by_params(self, params, name):
        """
        Create pc-dimm device from params.
        """
        params = params.object_params("dimm")
        dimm_type = "nvdimm" if params.get("nv_backend") else "pc-dimm"
        attrs = qdevices.Dimm.__attributes__[:]
        dev = qdevices.Dimm(params=params.copy_from_keys(attrs),
                            dimm_type=dimm_type)
        dev.set_param("id", "%s-%s" % ("dimm", name))
        if dimm_type == "nvdimm" and params.get("nvdimm_uuid"):
            try:
                dev.set_param("uuid", uuid.UUID(params["nvdimm_uuid"]))
            except ValueError:
                nvdimm_uuid = params["nvdimm_uuid"]
                if nvdimm_uuid == "<auto>":
                    nvdimm_uuid = uuid.uuid5(uuid.NAMESPACE_OID, name)
                dev.set_param("uuid", nvdimm_uuid)
        for ext_k, ext_v in params.get_dict("dimm_extra_params").items():
            dev.set_param(ext_k, ext_v)
        return dev

    def memory_define_by_params(self, params, name):
        """
        Create memory modules by params, include memory object and
        pc-dimm devices.
        """
        params = params.object_params(name)
        devices = []
        if not self.has_device("pc-dimm"):
            logging.warn("'PC-DIMM' does not support by your qemu")
            return devices
        mem = self.memory_object_define_by_params(params, name)
        if mem:
            devices.append(mem)
            use_mem = params.object_params(name).get("use_mem", "yes")
            if use_mem == "yes":
                dimm = self.dimm_device_define_by_params(params, name)
                dimm.set_param("memdev", mem.get_qid())
                devices.append(dimm)
        return devices

    def input_define_by_params(self, params, name, bus=None):
        """
        Create input device by params.

        :param params: VM params.
        :param name: Object name of input device.
        :param bus: Parent bus.
        """
        params = params.object_params(name)
        dev_map = {"mouse": {"virtio": "virtio-mouse"},
                   "keyboard": {"virtio": "virtio-keyboard"},
                   "tablet": {"virtio": "virtio-tablet"}}
        dev_type = params["input_dev_type"]
        bus_type = params["input_dev_bus_type"]
        driver = dev_map.get(dev_type)
        if not driver:
            raise ValueError("unsupported input device type")
        driver = driver.get(bus_type)
        if not driver:
            raise ValueError("unsupported input device bus")

        machine_type = params.get("machine_type", "")
        qbus_type = "PCI"
        if machine_type.startswith("q35") or machine_type.startswith("arm64"):
            qbus_type = "PCIE"

        if bus_type == "virtio":
            if "-mmio:" in machine_type:
                driver += "-device"
                qbus_type = "virtio-bus"
            elif machine_type.startswith("s390"):
                driver += "-ccw"
                qbus_type = "virtio-bus"
            else:
                driver += "-pci"

        if bus is None:
            bus = {"type": qbus_type}
        devices = []
        if self.has_device(driver):
            dev = qdevices.QDevice(driver, parent_bus=bus)
            dev.set_param("id", "input_%s" % name)
            devices.append(dev)
        else:
            logging.warn("'%s' is not supported by your qemu", driver)

        return devices

    def vcpu_device_define_by_params(self, params, name):
        """
        Create vcpu device by params.
        :param params: vcpu device params.
        :param name: Object name of vcpu device.
        """
        params = params.object_params(name)
        cpu_driver = params["cpu_driver"]
        if not self.has_device(cpu_driver):
            raise virt_vm.VMDeviceNotSupportedError(self.vmname, cpu_driver)
        vcpu_params = {"id": params.get("vcpu_id", name)}
        # Uses JSON format to update vcpu properties. e.g. {"node-id": 0}
        vcpu_props = json.loads(params.get("vcpu_props", "{}"))
        vcpu_params.update(vcpu_props)

        vcpu_dev = qdevices.QCPUDevice(cpu_driver,
                                       params.get_boolean("vcpu_enable"),
                                       params=vcpu_params,
                                       parent_bus={"aobject": "vcpu"})
        return vcpu_dev

    def fs_define_by_params(self, name, params, bus=None):
        """
        Create filesystem devices by params.

        :param name: Object name of filesystem device.
        :type name: str
        :param params: Filesystem device params.
        :type params: dict
        :param bus: Parent bus.
        :type bus: dict
        :return: List of corresponding filesystem devices.
        :rtype: list
        """
        driver = params["fs_driver"]
        target = params["fs_target"]
        fs_type = params.get('fs_source_type', 'mount')

        if fs_type == 'mount':
            source = params.get("fs_source_dir")
            base_dir = params.get("fs_source_base_dir", data_dir.get_data_dir())
            if not os.path.isabs(source):
                source = os.path.join(base_dir, source)

        machine_type = params.get("machine_type", "")
        qbus_type = "PCI"
        if machine_type.startswith("q35") or machine_type.startswith("arm64"):
            qbus_type = "PCIE"

        devices = []
        if driver == "virtio-fs":
            binary = params.get("fs_binary", "/usr/libexec/virtiofsd")
            extra_options = params.get("fs_binary_extra_options")
            sock_path = os.path.join(data_dir.get_tmp_dir(),
                                     '-'.join((self.vmname, name, 'virtiofsd.sock')))
            vfsd = qdevices.QVirtioFSDev(name, binary, sock_path,
                                         source, extra_options)
            devices.append(vfsd)

            char_params = Params()
            char_params["backend"] = "socket"
            char_params["id"] = 'char_%s' % vfsd.get_qid()
            sock_bus = {'busid': sock_path}
            char = qdevices.CharDevice(char_params, parent_bus=sock_bus)
            char.set_aid(vfsd.get_aid())
            devices.append(char)

            qdriver = "vhost-user-fs"
            if "-mmio:" in machine_type:
                qdriver += "-device"
                qbus_type = "virtio-bus"
            elif machine_type.startswith("s390"):
                qdriver += "-ccw"
                qbus_type = "virtio-bus"
            else:
                qdriver += "-pci"

            if bus is None:
                bus = {"type": qbus_type}

            dev_params = {"id": "vufs_%s" % vfsd.get_qid(),
                          "chardev": char.get_qid(),
                          "tag": target}
            fs_driver_props = json.loads(params.get("fs_driver_props", "{}"))
            dev_params.update(fs_driver_props)
            vufs = qdevices.QDevice(qdriver, params=dev_params, parent_bus=bus)
            vufs.set_aid(vfsd.get_aid())
            devices.append(vufs)
        else:
            raise ValueError("unsupported filesystem driver type")
        return devices
