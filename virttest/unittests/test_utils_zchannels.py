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

import unittest

try:
    from unittest import mock
except ImportError:
    import mock

import virttest
from virttest.utils_zchannels import ChannelPaths, SubchannelPaths

OUT_OK = ["Device   Subchan.  DevType CU Type Use  PIM PAM POM  CHPIDs           ",
          "----------------------------------------------------------------------",
          "0.0.0600 0.0.0000  1732/01 1731/01 yes  80  80  ff   17000000 00000000",
          "0.0.0601 0.0.0001  1732/01 1731/01 yes  80  80  ff   17000000 00000000",
          "0.0.0602 0.0.0002  1732/01 1731/01 yes  80  80  ff   17000000 00000000",
          "0.0.540c 0.0.24ac  3390/0c 3990/e9 yes  f0  f0  ff   01021112 00000000",
          "0.0.540d 0.0.24ad  3390/0c 3990/e9 yes  f0  f0  ff   01021112 00000000",
          "none     0.0.26aa                       f0  f0  ff   11122122 00000000",
          "none     0.0.26ab                       f0  f0  ff   11122122 00000000",
          "0.0.570c 0.0.27ac  3390/0c 3990/e9 yes  f0  f0  ff   12212231 00000000"]


class TestSubchannelPaths(unittest.TestCase):

    def test_get_info(self):
        virttest.utils_zchannels.cmd_status_output = mock.Mock(return_value=(0,
                                                               "\n".join(OUT_OK)))
        subchannel_paths = SubchannelPaths()
        subchannel_paths.get_info()
        self.assertEqual(8, len(subchannel_paths.devices))

    def test_get_first_unused_and_safely_removable(self):
        virttest.utils_zchannels.cmd_status_output = mock.Mock(return_value=(0,
                                                               "\n".join(OUT_OK)))
        subchannel_paths = SubchannelPaths()
        subchannel_paths.get_info()
        device = subchannel_paths.get_first_unused_and_safely_removable()
        self.assertIsNotNone(device)
        self.assertEqual("0.0.26aa", device[1])

    def test_get_first_unused_and_safely_removable_not_safe(self):
        not_safe = OUT_OK.copy()
        not_safe[6] = not_safe[6].replace("01021112", "11122122")
        virttest.utils_zchannels.cmd_status_output = mock.Mock(return_value=(0,
                                                               "\n".join(not_safe)))
        subchannel_paths = SubchannelPaths()
        subchannel_paths.get_info()
        device = subchannel_paths.get_first_unused_and_safely_removable()
        self.assertIsNone(device)

    def test_get_first_unused_and_safely_removable_not_first(self):
        not_safe = OUT_OK.copy()
        not_safe[7] = not_safe[7].replace("11122122", "01021112")
        virttest.utils_zchannels.cmd_status_output = mock.Mock(return_value=(0,
                                                               "\n".join(not_safe)))
        subchannel_paths = SubchannelPaths()
        subchannel_paths.get_info()
        device = subchannel_paths.get_first_unused_and_safely_removable()
        self.assertIsNotNone(device)
        self.assertEqual("0.0.26ab", device[1])


class TestChannelPaths(unittest.TestCase):

    def test__split(self):
        chpids = "12345678"
        ids = ChannelPaths._split(chpids)
        self.assertEqual(4, len(ids))
        self.assertEqual("0.12", ids[0])
        self.assertEqual("0.78", ids[3])


if __name__ == '__main__':
    unittest.main()
