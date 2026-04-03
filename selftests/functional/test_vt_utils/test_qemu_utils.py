import os
import subprocess
import unittest

from virttest.vt_utils import qemu_utils as qemu


class QemuFunctionalTest(unittest.TestCase):
    """Functional tests for autils.hypervisor.qemu module"""

    def setUp(self):
        super().setUp()
        self.available_qemu_paths = self._get_available_qemu_paths()

    def _get_available_qemu_paths(self):
        """Get the available qemu paths on the system"""
        qemu_paths = [
            "/usr/bin/qemu-kvm",
            "/usr/bin/qemu-system-x86_64",
            "/usr/libexec/qemu-kvm",
            "/usr/bin/qemu",
        ]

        available_qemu_paths = []

        for path in qemu_paths:
            if os.path.exists(path):
                try:
                    result = subprocess.run(
                        [path, "-help"], capture_output=True, timeout=10, check=False
                    )
                    if not result.returncode:
                        available_qemu_paths.append(path)
                except (subprocess.TimeoutExpired, FileNotFoundError):
                    continue
        return available_qemu_paths

    def test_has_option_with_real_qemu(self):
        """Test has_option function with real QEMU binary"""
        if not self.available_qemu_paths:
            self.skipTest("QEMU not available on system")

        default_qemu_path = "/usr/bin/qemu-kvm"
        if default_qemu_path not in self.available_qemu_paths:
            self.skipTest(
                f"The default qemu path: {default_qemu_path} not available on system"
            )

        # Test common options that should exist in most QEMU versions
        self.assertTrue(qemu.has_option("h"))
        self.assertTrue(qemu.has_option("version"))

        # Test option that should not exist
        self.assertFalse(qemu.has_option("nonexistent-option-12345"))

    def test_has_option_with_custom_path(self):
        """Test has_option with custom QEMU path"""
        # Find an available QEMU binary
        qemu_paths = [
            "/usr/bin/qemu-system-x86_64",
            "/usr/libexec/qemu-kvm",
            "/usr/bin/qemu",
        ]

        available_path = None
        for path in qemu_paths:
            if os.path.exists(path):
                available_path = path
                break

        if not available_path:
            self.skipTest(
                f"The custom qemu paths: {qemu_paths} not available on system"
            )

        if available_path:
            result = qemu.has_option("h", available_path)
            self.assertTrue(result)

    def test_get_support_machine_type_with_real_qemu(self):
        """Test get_support_machine_type function with real QEMU binary"""
        if not self.available_qemu_paths:
            self.skipTest("QEMU not available on system")

        names, types, aliases = qemu.get_support_machine_type(
            self.available_qemu_paths[0]
        )

        # Verify return types
        self.assertIsInstance(names, list)
        self.assertIsInstance(types, list)
        self.assertIsInstance(aliases, list)

        # All lists should have the same length
        self.assertEqual(len(names), len(types))
        self.assertEqual(len(names), len(aliases))

        # Should have at least one machine type
        self.assertGreater(len(names), 0)

        # Each name should be a string
        for name in names:
            self.assertIsInstance(name, str)
            self.assertGreater(len(name), 0)

        # Each type should be a string
        for machine_type in types:
            self.assertIsInstance(machine_type, str)

        # Aliases can be None or strings
        for alias in aliases:
            self.assertTrue(alias is None or isinstance(alias, str))

    def test_get_support_machine_type_remove_alias(self):
        """Test get_support_machine_type with remove_alias=True"""
        if not self.available_qemu_paths:
            self.skipTest("QEMU not available on system")

        _, _, aliases = qemu.get_support_machine_type(
            self.available_qemu_paths[0], remove_alias=True
        )

        # With remove_alias=True, all aliases should be None
        for alias in aliases:
            self.assertIsNone(alias)

    def test_get_support_machine_type_no_none_machines(self):
        """Test that 'none' machines are filtered out"""
        if not self.available_qemu_paths:
            self.skipTest("QEMU not available on system")

        names, _, _ = qemu.get_support_machine_type(self.available_qemu_paths[0])

        # Should not contain 'none' in machine names
        self.assertNotIn("none", names)

    def test_has_option_invalid_qemu_path(self):
        """Test has_option with invalid QEMU path"""
        result = qemu.has_option("help", "/nonexistent/qemu/path")
        # Should handle the error gracefully and return False
        self.assertFalse(result)

    def test_get_support_machine_type_invalid_path(self):
        """Test get_support_machine_type with invalid QEMU path"""
        with self.assertRaises((subprocess.CalledProcessError, FileNotFoundError)):
            qemu.get_support_machine_type("/nonexistent/qemu/path")


if __name__ == "__main__":
    unittest.main()
