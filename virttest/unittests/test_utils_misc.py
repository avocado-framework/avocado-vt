import logging
import unittest

from virttest import utils_misc

LOG = logging.getLogger("avocado." + __name__)


class TestDmesgFilter(unittest.TestCase):
    def test__remove_dmesg_matches(self):
        messages = "msg_1\nmsg_2\nmsg_3\nmsg_4"
        expected_dmesg = "'^msg_1$', '^msg_4$'"
        result = utils_misc._remove_dmesg_matches(messages, expected_dmesg)
        self.assertTrue(len(result), 2)
        self.assertTrue("msg_2" in result)
        self.assertTrue("msg_3" in result)


if __name__ == "__main__":
    unittest.main()
