import os
import tempfile
import unittest
from pathlib import Path
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

    def test_autoinstall_uses_http_even_with_answer_disk(self):
        for suffix in (".yaml", ".yml"):
            with self.subTest(suffix=suffix):
                config = self._config("cdrom")
                config.unattended_file = "answer" + suffix
                config.cdrom_unattended = "answer.iso"
                config.setup()
                config.setup_boot_disk.assert_not_called()
                config.setup_unattended_http_server.assert_called_once_with()


class AutoinstallHTTPTest(unittest.TestCase):
    def setUp(self):
        tmpdir = tempfile.TemporaryDirectory(prefix="vt-autoinstall-")
        self.addCleanup(tmpdir.cleanup)
        self.root = Path(tmpdir.name)
        self.config = unattended_install.UnattendedInstallConfig.__new__(
            unattended_install.UnattendedInstallConfig
        )
        self.config.tmpdir = str(self.root / "http")
        Path(self.config.tmpdir).mkdir()
        self.config.unattended_file = str(self.root / "answer.yaml")
        Path(self.config.unattended_file).write_text(
            "#cloud-config\nautoinstall:\n  version: 1\n"
        )
        self.config.unattended_server_port = None
        self.config.url_auto_content_ip = "192.0.2.1"
        self.config.kernel_params = "console=ttyS0,115200 console=tty0"
        server = mock.patch.object(unattended_install, "start_unattended_server_thread")
        self.server = server.start()
        self.addCleanup(server.stop)
        ports = mock.patch.object(
            unattended_install.utils_misc, "find_free_port", return_value=8001
        )
        self.find_port = ports.start()
        self.addCleanup(ports.stop)

    def test_serves_nocloud_seed_and_sets_kernel_parameters(self):
        self.config.setup_unattended_http_server()
        self.assertEqual(
            (Path(self.config.tmpdir) / "user-data").read_bytes(),
            Path(self.config.unattended_file).read_bytes(),
        )
        self.assertEqual(
            (Path(self.config.tmpdir) / "meta-data").read_text(),
            "instance-id: avocado-vt\n",
        )
        self.server.assert_called_once_with(8001, self.config.tmpdir)
        self.assertEqual(
            self.config.kernel_params.split(),
            [
                "console=ttyS0,115200",
                "console=tty0",
                "autoinstall",
                "ds=nocloud-net;s=http://192.0.2.1:8001/",
            ],
        )

    def test_replaces_previous_datasource_without_duplicate_flags(self):
        self.config.kernel_params += " autoinstall ds=nocloud-net;s=http://old/"
        self.config.setup_unattended_http_server()
        self.config.setup_unattended_http_server()
        tokens = self.config.kernel_params.split()
        self.assertEqual(tokens.count("autoinstall"), 1)
        self.assertEqual(
            [token for token in tokens if token.startswith("ds=")],
            ["ds=nocloud-net;s=http://192.0.2.1:8001/"],
        )
        self.find_port.assert_called_once_with(8000, 8099, "192.0.2.1")

    def test_requires_cloud_config_header(self):
        Path(self.config.unattended_file).write_text("autoinstall:\n  version: 1\n")
        with self.assertRaisesRegex(ValueError, "#cloud-config"):
            self.config.setup_unattended_http_server()
        self.server.assert_not_called()

    def test_legacy_http_delivery_is_preserved(self):
        for suffix in (".ks", ".preseed"):
            with self.subTest(suffix=suffix):
                self.config.unattended_file = "answer" + suffix
                self.config.kernel_params = "console=ttyS0 ks=http://old/ks.cfg"
                self.config.unattended_file_kernel_param_name = "ks"
                with mock.patch.object(self.config, "answer_kickstart") as answer:
                    self.config.setup_unattended_http_server()
                answer.assert_called_once_with(
                    os.path.join(self.config.tmpdir, "ks.cfg")
                )
                self.assertEqual(
                    self.config.kernel_params,
                    "console=ttyS0 ks=http://192.0.2.1:8001/ks.cfg",
                )

    def test_autoinstall_does_not_remaster_cdrom_initrd(self):
        self.config.params = {"vm_type": "qemu"}
        self.config.image_path = str(self.root / "images")
        self.config.kernel = os.path.join(self.config.image_path, "vmlinuz")
        self.config.initrd = os.path.join(self.config.image_path, "initrd")
        self.config.boot_path = "casper"
        self.config.cdrom_cd1 = "ubuntu.iso"
        original = b"original Ubuntu initramfs"

        def copy(_source, destination):
            Path(destination).write_bytes(original)

        image = mock.Mock()
        image.copy.side_effect = copy
        with mock.patch.object(
            unattended_install.iso9660, "iso9660", return_value=image
        ):
            with mock.patch.object(self.config, "preseed_initrd") as preseed:
                self.config.setup_cdrom()
        preseed.assert_not_called()
        self.assertEqual(Path(self.config.initrd).read_bytes(), original)
        image.copy.assert_has_calls(
            [
                mock.call("casper/vmlinuz", self.config.kernel),
                mock.call("casper/initrd", self.config.initrd),
            ]
        )


if __name__ == "__main__":
    unittest.main()
