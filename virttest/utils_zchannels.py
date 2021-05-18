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
Module for channel device management on s390x aka IBM Z

Example:
    # Retrieve device to remove it from host

    subchannel_paths = SubchannelPaths()
    subchannel_paths.get_info()

    device = subchannel_paths.get_first_unused_and_safely_removable()
    chpids = device[subchannel_paths.header["CHPIDs"]]

    channel_paths = ChannelPaths()
    channel_paths.set_standby(chipds)
"""
from virttest.utils_misc import cmd_status_output

# timeout value in seconds for any command run in this module
CMD_TIMEOUT = 60
# for debugging, set True to get verbose command run output
VERBOSE = False


class SubchannelPaths(object):
    """
    Represents channel subsystem info
    """

    HEADER = {
            "Device": 0,
            "Subchan.": 1,
            "DevType": 2,
            "CU Type": 3,
            "Use": 4,
            "PIM": 5,
            "PAM": 6,
            "POM": 7,
            "CHPIDs": 8,
            "CHPIDs_extra": 9
            }

    def __init__(self, session=None):
        """
        Initializes instance

        :param session: guest session; if None, host info is handled
        """
        self.session = session
        self.devices = []

    def get_info(self):
        """
        Calls lscss and stores lines
        """
        err, out = cmd_status_output("lscss", shell=True,
                                     session=self.session,
                                     timeout=CMD_TIMEOUT,
                                     verbose=VERBOSE)
        if err:
            raise OSError("Error when running lscss: %s" % out)
        # skip header and split according to HEADER
        self.devices = [[
            x[:8],
            x[9:17],
            x[19:26],
            x[27:34],
            x[35:38],
            x[40:42],
            x[44:46],
            x[48:50],
            x[53:61],
            x[62:]] for x in out.split("\n")[2:]]

    def get_first_unused_and_safely_removable(self):
        """
        Returns device subchannel id of the first unused device that
        does not share all channel path ids with any other used device.

        Requires get_info() to be called first.
        """
        used = [x for x in self.devices if x[self.HEADER["Use"]] == "yes"]
        unused = [x for x in self.devices if x not in used]
        index = self.HEADER["CHPIDs"]
        for device in unused:
            full_chpid_match = [x for x in used
                                if x[index] == device[index]]
            if full_chpid_match:
                continue
            return device
        return None


class ChannelPaths(object):
    """
    Represents channel path info
    """

    @staticmethod
    def _split(chpids):
        """
        Splits the string into pairs of two digits.

        :param chpids: string of concatenated chipds, e.g. "11122122"
        :return: list with ids, e.g. ["0.11", "0.12", "0.21", "0.22"]
        """

        if len(chpids) % 2 != 0:
            raise ValueError("%s is not a valid string of"
                             " of concatenated chpids" % chpids)
        ids = []
        for i in range(0, len(chpids), 2):
            ids.append("0.%s" % chpids[i:i+2])
        return ids

    @staticmethod
    def set_standby(chpids):
        """
        Sets all two digit chip ids standby.

        WARNING: Be careful of using this function.
        Setting all chipds of a device removes the device fully.
        A simple reboot won't restore them.

        :param chpids: string of concatenated chipds, e.g. "11122122"
        :raises OSError: if some command call fails
        """

        ids = ChannelPaths._split(chpids)
        for i in ids:
            err, out = cmd_status_output("chchp -c 0 %s" % i,
                                         shell=True,
                                         timeout=CMD_TIMEOUT,
                                         verbose=VERBOSE)
            if err:
                raise OSError("Couldn't set all channel paths standby."
                              " %s" % out)

    @staticmethod
    def set_online(chpids):
        """
        Sets all two digit chip ids configured.

        :param chpids: string of concatenated chipds, e.g. "11122122"
        :raises OSError: if some command call fails
        """

        ids = ChannelPaths._split(chpids)
        for i in ids:
            err, out = cmd_status_output("chchp -c 1 %s" % i,
                                         shell=True,
                                         timeout=CMD_TIMEOUT,
                                         verbose=VERBOSE)
            if err:
                raise OSError("Couldn't set all channel paths configured."
                              " %s" % out)
