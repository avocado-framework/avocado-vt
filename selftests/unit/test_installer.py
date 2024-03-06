#!/usr/bin/python

import os
import sys
import unittest

# simple magic for using scripts within a source tree
basedir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.isdir(os.path.join(basedir, "virttest")):
    sys.path.append(basedir)

from virttest import cartesian_config, installer


class installer_test(unittest.TestCase):
    def setUp(self):
        self.registry = installer.InstallerRegistry()

    def test_register_get_installer(self):
        install_mode = "custom_install_mode"
        virt_type = "custom_virt_type"

        class CustomVirtInstaller:
            pass

        self.registry.register(install_mode, CustomVirtInstaller, virt_type)
        klass = self.registry.get_installer(install_mode, virt_type)
        self.assertTrue(klass is CustomVirtInstaller)

    def test_register_get_installer_default(self):
        install_mode = "base_install_mode"

        class BaseVirtInstaller:
            pass

        self.registry.register(install_mode, BaseVirtInstaller)
        klass = self.registry.get_installer(install_mode, get_default_virt=True)
        self.assertTrue(klass is BaseVirtInstaller)

        klass = self.registry.get_installer(
            install_mode, virt=None, get_default_virt=True
        )
        self.assertTrue(klass is BaseVirtInstaller)

    def test_make_installer(self):
        config = """install_mode = test_install_mode
vm_type = test"""

        class Installer:
            def __init__(self, mode, name, test, params):
                pass

        installer.INSTALLER_REGISTRY.register("test_install_mode", Installer, "test")

        config_parser = cartesian_config.Parser()
        config_parser.parse_string(config)
        params = next(config_parser.get_dicts())

        instance = installer.make_installer("test_install_mode_test", params)
        self.assertTrue(isinstance(instance, Installer))


if __name__ == "__main__":
    unittest.main()
