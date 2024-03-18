import importlib
import os
import tempfile
import unittest

from selftests import BASEDIR


class VtInitTest(unittest.TestCase):
    @staticmethod
    def _swap():
        data_dir = os.path.join(BASEDIR, "selftests", ".data")
        config_file = os.path.join(BASEDIR, "avocado_vt", "conf.d", "vt.conf")
        config_test_file = os.path.join(data_dir, "vt_test.conf")
        tmp, tmp_name = tempfile.mkstemp(suffix=".conf", dir=data_dir)
        os.rename(config_test_file, tmp_name)
        os.rename(config_file, config_test_file)
        os.rename(tmp_name, config_file)

    def setUp(self):
        self._swap()

    def test_early_settings(self):
        """
        This test checks the initialization of vt options in early stage.
        When the `avocado.core.settings` is imported the vt plugin is
        initialized.
        """
        settings = getattr(importlib.import_module("avocado.core.settings"), "settings")
        tmp_dir = settings.as_dict().get("vt.common.tmp_dir", "")
        address_pool_filename = getattr(
            importlib.import_module("virttest.utils_net"), "ADDRESS_POOL_FILENAME"
        )
        self.assertEqual(tmp_dir, "/tmp")
        self.assertEqual(address_pool_filename, "/tmp/address_pool")

    def tearDown(self):
        self._swap()


if __name__ == "__main__":
    unittest.main()
