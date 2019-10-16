import unittest
from unittest import mock

from virttest.tests import unattended_install


class UnattendedInstallSetupTest(unittest.TestCase):
    def _config(self, medium):
        config = unattended_install.UnattendedInstallConfig.__new__(
            unattended_install.UnattendedInstallConfig
        )
        config.medium = medium
        config.syslog_server_enabled = "no"
        config.kernel = "vmlinuz"
        config.initrd = "initrd"
        config.unattended_file = "answer.preseed"
        config.floppy = ""
        config.cdrom_unattended = ""
        config.params = {}
        config.attributes = []
        for method in (
            "setup_cdrom",
            "setup_url",
            "setup_nfs",
            "setup_boot_disk",
            "setup_unattended_http_server",
        ):
            setattr(config, method, mock.Mock())
        return config

    def test_network_preseed_uses_http(self):
        for medium in ("url", "nfs"):
            with self.subTest(medium=medium):
                config = self._config(medium)
                config.setup()
                config.setup_unattended_http_server.assert_called_once_with()

    def test_embedded_preseed_needs_no_extra_delivery(self):
        for medium in ("cdrom", "kernel_initrd"):
            with self.subTest(medium=medium):
                config = self._config(medium)
                config.cdrom_unattended = "answer.iso"
                config.setup()
                config.setup_cdrom.assert_called_once_with()
                config.setup_boot_disk.assert_not_called()
                config.setup_unattended_http_server.assert_not_called()

    def test_preseed_without_initrd_uses_http(self):
        config = self._config("cdrom")
        config.initrd = ""
        config.setup()
        config.setup_unattended_http_server.assert_called_once_with()

    def test_kickstart_still_uses_boot_disk(self):
        config = self._config("cdrom")
        config.unattended_file = "answer.ks"
        config.cdrom_unattended = "answer.iso"
        config.setup()
        config.setup_boot_disk.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
