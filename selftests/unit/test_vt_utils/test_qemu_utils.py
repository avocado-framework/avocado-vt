import unittest.mock

from virttest.vt_utils import qemu_utils as qemu


class HasOptionTest(unittest.TestCase):
    @unittest.mock.patch("autils.devel.process.run")
    def test_has_option_found(self, mock_process_run):
        mock_cmd_result = unittest.mock.MagicMock()
        mock_cmd_result.stdout_text = (
            "-netdev    specify the network backend\n"
            "-device    add device\n"
            "-enable-kvm enable KVM acceleration\n"
        )
        mock_process_run.return_value = mock_cmd_result

        result = qemu.has_option("netdev")

        mock_process_run.assert_called_once_with(
            "/usr/bin/qemu-kvm -help", shell=True, ignore_status=True, verbose=False
        )
        self.assertTrue(result)

    @unittest.mock.patch("autils.devel.process.run")
    def test_has_option_not_found(self, mock_process_run):
        mock_cmd_result = unittest.mock.MagicMock()
        mock_cmd_result.stdout_text = (
            "-netdev    specify the network backend\n"
            "-device    add device\n"
            "-enable-kvm enable KVM acceleration\n"
        )
        mock_process_run.return_value = mock_cmd_result

        result = qemu.has_option("nonexistent")

        mock_process_run.assert_called_once_with(
            "/usr/bin/qemu-kvm -help", shell=True, ignore_status=True, verbose=False
        )
        self.assertFalse(result)

    @unittest.mock.patch("autils.devel.process.run")
    def test_has_option_custom_qemu_path(self, mock_process_run):
        mock_cmd_result = unittest.mock.MagicMock()
        mock_cmd_result.stdout_text = "-enable-kvm enable KVM acceleration\n"
        mock_process_run.return_value = mock_cmd_result

        result = qemu.has_option("enable-kvm", "/custom/path/qemu")

        mock_process_run.assert_called_once_with(
            "/custom/path/qemu -help", shell=True, ignore_status=True, verbose=False
        )
        self.assertTrue(result)

    @unittest.mock.patch("autils.devel.process.run")
    def test_has_option_regex_match_beginning_of_line(self, mock_process_run):
        mock_cmd_result = unittest.mock.MagicMock()
        mock_cmd_result.stdout_text = (
            "some text with enable-kvm in middle\n"
            "-enable-kvm enable KVM acceleration\n"
        )
        mock_process_run.return_value = mock_cmd_result

        result = qemu.has_option("enable-kvm")

        mock_process_run.assert_called_once_with(
            "/usr/bin/qemu-kvm -help", shell=True, ignore_status=True, verbose=False
        )
        self.assertTrue(result)

    @unittest.mock.patch("autils.devel.process.run")
    def test_has_option_regex_no_match_middle_of_line(self, mock_process_run):
        mock_cmd_result = unittest.mock.MagicMock()
        mock_cmd_result.stdout_text = (
            "some text with enable-kvm in middle\nother line\n"
        )
        mock_process_run.return_value = mock_cmd_result

        result = qemu.has_option("enable-kvm")
        mock_process_run.assert_called_once_with(
            "/usr/bin/qemu-kvm -help", shell=True, ignore_status=True, verbose=False
        )
        self.assertFalse(result)

    @unittest.mock.patch("autils.devel.process.run")
    def test_has_option_with_space_after(self, mock_process_run):
        mock_cmd_result = unittest.mock.MagicMock()
        mock_cmd_result.stdout_text = "-device TYPE[,PROP=VALUE,...]  add device\n"
        mock_process_run.return_value = mock_cmd_result

        result = qemu.has_option("device")
        mock_process_run.assert_called_once_with(
            "/usr/bin/qemu-kvm -help", shell=True, ignore_status=True, verbose=False
        )
        self.assertTrue(result)

    @unittest.mock.patch("autils.devel.process.run")
    def test_has_option_at_end_of_line(self, mock_process_run):
        mock_cmd_result = unittest.mock.MagicMock()
        mock_cmd_result.stdout_text = "-h\n-help\n"
        mock_process_run.return_value = mock_cmd_result

        result = qemu.has_option("h")

        mock_process_run.assert_called_once_with(
            "/usr/bin/qemu-kvm -help", shell=True, ignore_status=True, verbose=False
        )
        self.assertTrue(result)

    @unittest.mock.patch("autils.devel.process.run")
    def test_has_option_with_invalid_qemu_path(self, mock_process_run):
        mock_cmd_result = unittest.mock.MagicMock()
        mock_cmd_result.stdout_text = ""
        mock_process_run.return_value = mock_cmd_result

        result = qemu.has_option("help", "/custom/invalid_path/qemu")

        mock_process_run.assert_called_once_with(
            "/custom/invalid_path/qemu -help",
            shell=True,
            ignore_status=True,
            verbose=False,
        )
        self.assertFalse(result)


class GetSupportMachineTypeTest(unittest.TestCase):
    @unittest.mock.patch("autils.devel.process.run")
    def test_get_support_machine_type_basic(self, mock_process_run):
        mock_cmd_result = unittest.mock.MagicMock()
        mock_cmd_result.stdout_text = """Supported machines are:
pc-i440fx-8.2       Standard PC (i440FX + PIIX, 1996) (alias of pc)
pc-i440fx-8.1       Standard PC (i440FX + PIIX, 1996)
pc-q35-8.2         Standard PC (Q35 + ICH9, 2009) (alias of q35) (default)
none                empty machine
"""
        mock_process_run.return_value = mock_cmd_result

        names, types, aliases = qemu.get_support_machine_type()

        mock_process_run.assert_called_once_with("/usr/libexec/qemu-kvm -M ?")
        self.assertEqual(names, ["pc-i440fx-8.2", "pc-i440fx-8.1", "pc-q35-8.2"])
        self.assertEqual(
            types,
            [
                "Standard PC (i440FX + PIIX, 1996)",
                "Standard PC (i440FX + PIIX, 1996)",
                "Standard PC (Q35 + ICH9, 2009)",
            ],
        )
        self.assertEqual(aliases, ["(alias of pc)", None, "(alias of q35) (default)"])

    @unittest.mock.patch("autils.devel.process.run")
    def test_get_support_machine_type_custom_binary(self, mock_process_run):
        mock_cmd_result = unittest.mock.MagicMock()
        mock_cmd_result.stdout_text = """Supported machines are:
pc-i440fx-8.2       Standard PC (i440FX + PIIX, 1996)
"""
        mock_process_run.return_value = mock_cmd_result

        names, types, aliases = qemu.get_support_machine_type("/custom/qemu-binary")

        mock_process_run.assert_called_once_with("/custom/qemu-binary -M ?")
        self.assertEqual(names, ["pc-i440fx-8.2"])
        self.assertEqual(types, ["Standard PC (i440FX + PIIX, 1996)"])
        self.assertEqual(aliases, [None])

    @unittest.mock.patch("autils.devel.process.run")
    def test_get_support_machine_type_remove_alias(self, mock_process_run):
        mock_cmd_result = unittest.mock.MagicMock()
        mock_cmd_result.stdout_text = """Supported machines are:
pc-i440fx-8.2       Standard PC (i440FX + PIIX, 1996) (alias of pc)
pc-q35-8.2         Standard PC (Q35 + ICH9, 2009) (default)
none                empty machine
"""
        mock_process_run.return_value = mock_cmd_result

        names, types, aliases = qemu.get_support_machine_type(remove_alias=True)

        mock_process_run.assert_called_once_with("/usr/libexec/qemu-kvm -M ?")

        self.assertEqual(names, ["pc-i440fx-8.2", "pc-q35-8.2"])
        self.assertEqual(
            types,
            ["Standard PC (i440FX + PIIX, 1996)", "Standard PC (Q35 + ICH9, 2009)"],
        )
        self.assertEqual(aliases, [None, None])

    @unittest.mock.patch("autils.devel.process.run")
    def test_get_support_machine_type_skip_none(self, mock_process_run):
        mock_cmd_result = unittest.mock.MagicMock()
        mock_cmd_result.stdout_text = """Supported machines are:
pc-i440fx-8.2       Standard PC (i440FX + PIIX, 1996)
none                empty machine
pc-q35-8.2         Standard PC (Q35 + ICH9, 2009)
"""
        mock_process_run.return_value = mock_cmd_result

        names, types, aliases = qemu.get_support_machine_type()

        mock_process_run.assert_called_once_with("/usr/libexec/qemu-kvm -M ?")

        self.assertEqual(names, ["pc-i440fx-8.2", "pc-q35-8.2"])
        self.assertEqual(
            types,
            ["Standard PC (i440FX + PIIX, 1996)", "Standard PC (Q35 + ICH9, 2009)"],
        )
        self.assertEqual(aliases, [None, None])

    @unittest.mock.patch("autils.devel.process.run")
    def test_get_support_machine_type_with_deprecated(self, mock_process_run):
        mock_cmd_result = unittest.mock.MagicMock()
        mock_cmd_result.stdout_text = """Supported machines are:
pc-i440fx-8.2       Standard PC (i440FX + PIIX, 1996)
pc-i440fx-2.12      Standard PC (i440FX + PIIX, 1996) (deprecated)
"""
        mock_process_run.return_value = mock_cmd_result

        names, types, aliases = qemu.get_support_machine_type()

        mock_process_run.assert_called_once_with("/usr/libexec/qemu-kvm -M ?")

        self.assertEqual(names, ["pc-i440fx-8.2", "pc-i440fx-2.12"])
        self.assertEqual(
            types,
            ["Standard PC (i440FX + PIIX, 1996)", "Standard PC (i440FX + PIIX, 1996)"],
        )
        self.assertEqual(aliases, [None, "(deprecated)"])

    @unittest.mock.patch("autils.devel.process.run")
    def test_get_support_machine_type_complex_alias(self, mock_process_run):
        mock_cmd_result = unittest.mock.MagicMock()
        mock_cmd_result.stdout_text = """Supported machines are:
pc-q35-8.2         Standard PC (Q35 + ICH9, 2009) (alias of q35) (default)
microvm            microvm (i386)
"""
        mock_process_run.return_value = mock_cmd_result

        names, types, aliases = qemu.get_support_machine_type()

        mock_process_run.assert_called_once_with("/usr/libexec/qemu-kvm -M ?")

        self.assertEqual(names, ["pc-q35-8.2", "microvm"])
        self.assertEqual(types, ["Standard PC (Q35 + ICH9, 2009)", "microvm (i386)"])
        self.assertEqual(aliases, ["(alias of q35) (default)", None])

    @unittest.mock.patch("autils.devel.process.run")
    def test_get_support_machine_type_return_types(self, mock_process_run):
        mock_cmd_result = unittest.mock.MagicMock()
        mock_cmd_result.stdout_text = """Supported machines are:
pc-i440fx-8.2       Standard PC (i440FX + PIIX, 1996)
"""
        mock_process_run.return_value = mock_cmd_result

        result = qemu.get_support_machine_type()

        mock_process_run.assert_called_once_with("/usr/libexec/qemu-kvm -M ?")

        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 3)
        names, types, aliases = result
        self.assertIsInstance(names, list)
        self.assertIsInstance(types, list)
        self.assertIsInstance(aliases, list)


if __name__ == "__main__":
    unittest.main()
