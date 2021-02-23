# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#
# See LICENSE for more details.
#
# Copyright: Red Hat Inc. 2020
# Author: Sebastian Mitterle <smitterl@redhat.com>

"""
Module for crypto device management on s390x aka IBM Z

Example:

    # get available domains and set up host
    lszcrypt_info = CryptoDeviceInfoBuilder.get()
    mask_helper = APMaskHelper.from_infos(lszcrypt_info.domains)
    matrix_device = MatrixDevice.from_infos(lszcrypt_info.domains)
    ...
    # Use matrix_device.uuid for guest definition/device attachment
    # <hostdev ...><source><address uuid="$uuid"></source></hostdev>
    ...
    # restore host gracefully
    matrix_device.unassign_all()
    mask_helper.return_to_host_all()

"""
from uuid import uuid1
from os.path import join

from avocado.utils import process
from virttest.utils_misc import cmd_status_output

# timeout value in seconds for any command run
CMD_TIMEOUT = 60
# for debugging, set True to get verbose command run output
VERBOSE = False
# lszcrypt output if there are not crypto devices
NO_DEVICES = "No crypto card devices found"


class CryptoDeviceInfoBuilder(object):
    """
    Represents the available crypto device info
    """

    def __init__(self, session=None):
        """
        Initializes instance

        :param session: guest session; if None, host info is handled
        """
        self.session = session

    def get_info(self):
        """
        Gets crypto device info

        :return: CryptoDeviceInfo instance
        """
        info = CryptoDeviceInfo()
        err, out = cmd_status_output("lszcrypt -V", shell=True,
                                     session=self.session,
                                     timeout=CMD_TIMEOUT,
                                     verbose=VERBOSE)
        if err:
            if NO_DEVICES not in out:
                raise OSError("Error when running lszcrypt: %s" % out)
        else:
            out = out.strip().split('\n')[2:]
            for entry in out:
                info.append(entry)
        return info

    @staticmethod
    def get(session=None):
        """
        Gets crypto device info

        :param session: guest session, s. __init__ for details
        :return: CryptoDeviceInfo instance
        """
        builder = CryptoDeviceInfoBuilder(session)
        return builder.get_info()


class CryptoDeviceInfo(object):
    """
    Represents the crypto device info
    """

    def __init__(self):
        self._entries = []

    def append(self, lszcrypt_entry):
        """
        Append a new row on the table

        :param lszcrypt_entry: LszcryptRow instance
        :return: None
        """
        self._entries.append(CryptoDeviceInfoEntry.from_string(lszcrypt_entry))

    @property
    def entries(self):
        """
        Protect member from write

        :return: crypto device info entries
        """
        return self._entries

    @property
    def domains(self):
        """
        Returns only domain info entries

        :return: list of domain info entries
        """
        return [x for x in self._entries if x.domain]

    def __str__(self):
        s = "{_entries: "
        for e in self._entries:
            s += str(e.__dict__)
        s += "}"
        return s


class CryptoDeviceInfoEntry(object):
    """
    Represents a single device info entry
    """

    def __init__(self):
        self._card = None
        self._domain = None
        self.type = None
        self.mode = None
        self.status = None
        self.requests = None
        self.pending = None
        self.hwtype = None
        self.qdepth = None
        self.functions = None
        self.driver = None

    @property
    def id(self):
        """
        The id value as list [card], or [card, domain]
        :return: id value as list
        """
        return [self.card, self.domain] if self.domain else [self.card]

    @id.setter
    def id(self, id):
        if "." in id:
            parts = id.split(".")
            self._card, self._domain = parts[0], parts[1]
        else:
            self._card, self._domain = id, None

    @property
    def card(self):
        """
        The card property
        :return: card value
        """
        return self._card

    @property
    def domain(self):
        """
        The domain property

        :return: domain value
        """
        return self._domain

    @staticmethod
    def from_string(line):
        """
        Constructs a device info entry from lszcrypt

        :param line: lszcrypt output line
        :return: device info entry
        """
        r = CryptoDeviceInfoEntry()
        (r.id, r.type, r.mode, r.status, r.requests, r.pending,
         r.hwtype, r.qdepth, r.functions, r.driver) = line.split()
        return r


def _echo(value, sysfs):
    """
    echoes value into sysfs path

    :param value:
    :param sysfs:
    :raises RuntimeError: if operation fails
    :return: None
    """

    err, out = process.getstatusoutput("echo %s > %s" % (value, sysfs),
                                       timeout=CMD_TIMEOUT,
                                       verbose=VERBOSE)
    if err:
        raise RuntimeError("Couldn't set value '%s' on '%s': %s" % (
            value, sysfs, out
        ))


def load_vfio_ap():
    """
    Loads the passthrough module

    :return: None
    """
    err, out = process.getstatusoutput("modprobe vfio_ap",
                                       timeout=CMD_TIMEOUT,
                                       verbose=VERBOSE)
    if err:
        raise RuntimeError("Couldn't load vfio_ap: %s" % out)


def unload_vfio_ap():
    """
    Unloads the passthrough module

    :return: None
    """
    err, out = process.getstatusoutput("rmmod vfio_ap",
                                       timeout=CMD_TIMEOUT,
                                       verbose=VERBOSE)
    if err:
        raise RuntimeError("Couldn't unload vfio_ap: %s" % out)


# sysfs paths controlling device availability (s. kernel doc)
APMASK_SYSFS = "/sys/bus/ap/apmask"
AQMASK_SYSFS = "/sys/bus/ap/aqmask"


class APMaskHelper(object):
    """
    Handles crypto device masking
    """

    def __init__(self):
        """
        Initializes the class instance

        """
        self.masked = []

    def remove_from_host_all(self, infos):
        """
        Removes devices from host default driver

        :param infos: list of CryptoDeviceInfoEntry
        :return: None
        """
        for info in infos:
            self.remove_from_host(info)

    def remove_from_host(self, info):
        """
        Removes device from host default driver

        :param info: CryptoDeviceInfoEntry instance
        :return: None
        """
        _echo("-0x%s" % info.card, APMASK_SYSFS)
        if info.domain:
            _echo("-0x%s" % info.domain, AQMASK_SYSFS)
        self.masked.append(info)

    def return_to_host_all(self):
        """
        Returns devices to the host default driver

        :return: None
        """
        while self.masked:
            self.return_to_host(self.masked[-1])

    def return_to_host(self, info):
        """
        Returns device to the host default driver

        :param info: CryptoDeviceInfoEntry instance
        :return: None
        """
        _echo("+0x%s" % info.card, APMASK_SYSFS)
        if info.domain:
            _echo("+0x%s" % info.domain, AQMASK_SYSFS)
        self.masked.remove(info)

    @staticmethod
    def from_infos(infos):
        """
        Sets up a configuration helper with a matrix device where all passed
        devices are removed from host access and added to matrix device for
        passthrough.

        :param infos: list of CryptoDeviceInfoEntry
        :return: VfioConfigurationHelper instance
        """
        apmask_helper = APMaskHelper()
        apmask_helper.remove_from_host_all(infos)
        return apmask_helper


# sysfs path for the vfio-ap matrix devices
PASSTHROUGH_SYSFS = ("/sys/devices/vfio_ap/"
                     "matrix/mdev_supported_types/vfio_ap-passthrough/")


class MatrixDevice(object):
    """
    Represents the matrix device on sysfs
    """

    def __init__(self):
        """
        Sets up the matrix device that will be attached to guest
        """
        self.uuid = str(uuid1())
        _echo(self.uuid, join(PASSTHROUGH_SYSFS, "create"))
        self.path = join(PASSTHROUGH_SYSFS, "devices", self.uuid)
        self.assigned = []

    def remove(self):
        """Remove this matrix device on host"""
        _echo(1, join(self.path, "remove"))

    def assign_all(self, infos):
        """
        Assign all passed devices to the matrix

        :param infos: list of CryptoDeviceInfoEntry
        """
        for info in infos:
            self.assign(info)

    def assign(self, info):
        """
        Assign device to the matrix
        :param info: CryptoDeviceInfoEntry instance
        :return: None
        """
        _echo("0x%s" % info.card, join(self.path, "assign_adapter"))
        if info.domain:
            _echo("0x%s" % info.domain, join(self.path, "assign_domain"))
        self.assigned.append(info)

    def unassign(self, info):
        """
        Unassign device from the matrix
        :param info: CryptoDeviceInfoEntry instance
        :return: None
        """
        _echo("0x%s" % info.card, join(self.path, "unassign_adapter"))
        if info.domain:
            _echo("0x%s" % info.domain, join(self.path, "unassign_domain"))
        self.assigned.remove(info)

    def unassign_all(self):
        """
        Unassign all devices from the matrix

        :return: None
        """
        while self.assigned:
            self.unassign(self.assigned[-1])

    @staticmethod
    def from_infos(infos):
        """
        Creates a matrix device and assigns all passed devices

        :param infos: list of CryptoDeviceInfoEntry
        :return: MatrixDevice instance
        """
        matrix_dev = MatrixDevice()
        matrix_dev.assign_all(infos)
        return matrix_dev
