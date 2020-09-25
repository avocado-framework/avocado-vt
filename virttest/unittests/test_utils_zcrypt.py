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
from virttest.utils_zcrypt import CryptoDeviceInfoBuilder

OUT_OK = ("CARD.DOMAIN TYPE  MODE        STATUS  REQUESTS  PENDING HWTYPE QDEPTH FUNCTIONS  DRIVER     \n"
          "--------------------------------------------------------------------------------------------\n"
          "01          CEX5C CCA-Coproc  online         1        0     11     08 S--D--N--  cex4card   \n"
          "01.002c     CEX5C CCA-Coproc  online         1        0     11     08 S--D--N--  cex4queue  \n")

virttest.utils_zcrypt.cmd_status_output = mock.Mock(return_value=(0, OUT_OK))


class LszcryptCmd(unittest.TestCase):

    def setUp(self):
        self.info = CryptoDeviceInfoBuilder.get()

    def test_get_info_card(self):
        self.assertEqual("01", self.info.entries[0].card)

    def test_get_info_domain(self):
        self.assertEqual("002c", self.info.entries[1].domain)

    def test_get_info_last_driver(self):
        self.assertEqual("cex4queue", self.info.entries[1].driver)

    def test_get_domain(self):
        domains = self.info.domains
        self.assertEqual(len(domains), 1)
        self.assertEqual("002c", domains[0].domain)

    @mock.patch.object(virttest.utils_zcrypt, "cmd_status_output",
                       return_value=(1, virttest.utils_zcrypt.NO_DEVICES))
    def test_get_info_no_devices(self, *mocks):
        self.info = CryptoDeviceInfoBuilder.get()
        self.assertEqual(len(self.info.entries), 0)


if __name__ == '__main__':
    unittest.main()
