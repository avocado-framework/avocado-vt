#!/usr/bin/env python

import os
import sys
import tempfile

if sys.version_info[:2] == (2, 6):
    import unittest2 as unittest

    PYTHON_26 = True
else:
    import unittest

    PYTHON_26 = False

# simple magic for using scripts within a source tree
basedir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.isdir(os.path.join(basedir, "virttest")):
    sys.path.append(basedir)

from virttest import utils_config

# Test conf file content
content = """# This is a comment line.
a = 1
b = [hi, there]
c = hello
d = "hi, there"
e = [hi,
    there]

"""

# Expected changed conf file content
changed_content = """a = 1
b = [hi, there]
c = hello
d = "hi, there"
f = test

"""


class SectionlessConfigTest(unittest.TestCase):
    def test_accessers(self):
        config_file = tempfile.NamedTemporaryFile()
        config_path = config_file.name
        config_file.close()

        try:
            config_file = open(config_path, "w")
            config_file.write(content)
            config_file.close()

            # Test 'try...finally...' usage.
            config = utils_config.SectionlessConfig(config_path)
            try:
                # Test loader.
                self.assertEqual(len(config), 5)
                self.assertEqual(config["a"], "1")
                self.assertEqual(config["b"], "[hi, there]")
                self.assertEqual(config["c"], "hello")
                self.assertEqual(config["d"], '"hi, there"')
                self.assertEqual(config["e"], "[hi,\nthere]")

                # Test getter.
                try:
                    config["f"]
                except Exception as e:
                    self.assertEqual(utils_config.ConfigNoOptionError, e.__class__)
                    self.assertTrue("no option" in str(e))

                # Test setter.
                config["f"] = "test"
                self.assertEqual(config["f"], "test")

                # Test deleter.
                # delete exist option.
                del config["f"]
                # delete non-exist option.
                try:
                    del config["f"]
                except Exception as e:
                    self.assertEqual(utils_config.ConfigNoOptionError, e.__class__)
                    self.assertTrue("no option" in str(e))

                # Test contain.
                self.assertTrue("a" in config)
                self.assertFalse("f" in config)

            finally:
                config.restore()

            # Test 'with' usage.
            with utils_config.SectionlessConfig(config_path) as config:
                # Test loader.
                self.assertEqual(len(config), 5)
                self.assertEqual(config["a"], "1")
                self.assertEqual(config["b"], "[hi, there]")
                self.assertEqual(config["c"], "hello")
                self.assertEqual(config["d"], '"hi, there"')
                self.assertEqual(config["e"], "[hi,\nthere]")

                # Test getter.
                try:
                    config["f"]
                except Exception as e:
                    self.assertEqual(utils_config.ConfigNoOptionError, e.__class__)
                    self.assertTrue("no option" in str(e))

                # Test setter.
                config["f"] = "test"
                self.assertEqual(config["f"], "test")

                # Test deleter.
                del config["f"]
                try:
                    config["f"]
                except Exception as e:
                    self.assertEqual(utils_config.ConfigNoOptionError, e.__class__)
                    self.assertTrue("no option" in str(e))

                # Test contain.
                self.assertTrue("a" in config)
                self.assertFalse("f" in config)
        finally:
            os.remove(config_path)

    def test_specific_accessers(self):
        config_file = tempfile.NamedTemporaryFile()
        config_path = config_file.name
        config_file.close()

        try:
            config_file = open(config_path, "w")
            config_file.write(content)
            config_file.close()

            config = utils_config.SectionlessConfig(config_path)
            try:
                config.set_string("a", "Hi")
                self.assertEqual(config["a"], '"Hi"')
                self.assertEqual(config.get_string("a"), "Hi")
                config["a"] = "'Hi'"
                self.assertEqual(config.get_string("a"), "Hi")
                config["a"] = "Hi"
                self.assertRaises(ValueError, config.get_string, "a")
                config["a"] = '"Hi'
                self.assertRaises(ValueError, config.get_string, "a")

                config.set_int("a", 15)
                self.assertEqual(config["a"], "15")
                self.assertEqual(config.get_int("a"), 15)
                config.set_int("a", -15)
                self.assertEqual(config.get_int("a"), -15)
                config.set_string("a", "invalid")
                self.assertRaises(ValueError, config.get_float, "a")

                config.set_float("a", 15.123)
                self.assertEqual(config["a"], "15.123")
                self.assertEqual(config.get_float("a"), 15.123)
                config.set_string("a", "invalid")
                self.assertRaises(ValueError, config.get_float, "a")

                config.set_boolean("a", True)
                self.assertEqual(config["a"], "1")
                self.assertTrue(config.get_boolean("a"))
                config.set_string("a", "Yes")
                self.assertTrue(config.get_boolean("a"))
                config.set_string("a", "ON")
                self.assertTrue(config.get_boolean("a"))
                config.set_boolean("a", False)
                self.assertEqual(config["a"], "0")
                self.assertFalse(config.get_boolean("a"))
                config.set_string("a", "fAlSe")
                self.assertFalse(config.get_boolean("a"))
                config.set_string("a", "off")
                self.assertFalse(config.get_boolean("a"))
                config.set_string("a", "invalid")
                self.assertRaises(ValueError, config.get_boolean, "a")

                config.set_list("a", [15, "Hello"])
                self.assertEqual(config["a"], '["15", "Hello"]')
                config.set_list("a", [15, "Hello"])
                self.assertEqual(config.get_list("a"), ["15", "Hello"])
                config["a"] = '[15, \n     "Hello"]'
                self.assertEqual(config.get_list("a"), ["15", "Hello"])
                config["a"] = '[15, "Hi, there"]'
                self.assertEqual(config.get_list("a"), ["15", "Hi, there"])
            finally:
                config.restore()
        finally:
            os.remove(config_path)

    @unittest.skipIf(PYTHON_26, "Unreliable in python 2.6")
    def test_restore(self):
        config_file = tempfile.NamedTemporaryFile()
        config_path = config_file.name
        config_file.close()

        # Restore after use.
        try:
            config_file = open(config_path, "w")
            config_file.write(content)
            config_file.close()

            config = utils_config.SectionlessConfig(config_path)
            try:
                # Change the config.
                config["f"] = "test"
                self.assertEqual(config["f"], "test")
                del config["e"]
            finally:
                config.restore()
        finally:
            final_file = open(config_path)
            try:
                self.assertEqual(final_file.read(), content)
            finally:
                final_file.close()
            os.remove(config_path)

        # Don't restore after use.
        try:
            config_file = open(config_path, "w")
            config_file.write(content)
            config_file.close()

            config = utils_config.SectionlessConfig(config_path)

            # Change the config.
            config["f"] = "test"
            self.assertEqual(config["f"], "test")
            del config["e"]
        finally:
            final_file = open(config_path)
            try:
                self.assertEqual(final_file.read(), changed_content)
            finally:
                final_file.close()
            os.remove(config_path)

    @unittest.skipIf(PYTHON_26, "Unreliable in python 2.6")
    def test_sync_file(self):
        config_file = tempfile.NamedTemporaryFile()
        config_path = config_file.name
        config_file.close()

        try:
            config_file = open(config_path, "w")
            config_file.write(content)
            config_file.close()

            config = utils_config.SectionlessConfig(config_path)
            try:
                # Change the config.
                config["f"] = "test"
                self.assertEqual(config["f"], "test")
                del config["e"]

                # Test the change is applied to target file.
                cur_file = open(config_path)
                try:
                    self.assertEqual(cur_file.read(), changed_content)
                finally:
                    cur_file.close()
            finally:
                config.restore()
        finally:
            os.remove(config_path)


class LibvirtConfigCommonTest(unittest.TestCase):
    class UnimplementedConfig(utils_config.LibvirtConfigCommon):
        pass

    class NoTypesConfig(utils_config.LibvirtConfigCommon):
        conf_path = "/tmp/config_unittest.conf"

    class UndefinedTypeConfig(utils_config.LibvirtConfigCommon):
        __option_types__ = {
            "test": "invalid_type",
            "test2": "boolean",
        }
        conf_path = "/tmp/config_unittest.conf"

    def test_unimplemented(self):
        try:
            self.UnimplementedConfig()
        except Exception as e:
            self.assertEqual(utils_config.ConfigError, e.__class__)
            self.assertTrue("not set up" in str(e))

    def test_no_path(self):
        try:
            self.NoTypesConfig()
        except Exception as e:
            self.assertEqual(utils_config.ConfigError, e.__class__)
            self.assertTrue("not set up" in str(e))

    def test_undefined_type(self):
        try:
            config = self.UndefinedTypeConfig()
        except Exception as e:
            self.assertEqual(utils_config.ConfigError, e.__class__)
            self.assertTrue("don't exists" in str(e))

        try:
            config_file = open("/tmp/config_unittest.conf", "w")
            config_file.write("")
            config_file.close()

            config = self.UndefinedTypeConfig()

            # Test setter getter
            # Normal option
            config.test2 = True
            self.assertEqual(config.test2, True)
            # Repeat set option
            config.test2 = False
            self.assertEqual(config.test2, False)
            # Set unknown type
            try:
                config.test = "1"
            except Exception as e:
                self.assertEqual(
                    utils_config.LibvirtConfigUnknownKeyTypeError, e.__class__
                )
                self.assertTrue("Unknown type" in str(e))
            # Get unknown type
            try:
                print(config.test)
            except Exception as e:
                self.assertEqual(
                    utils_config.LibvirtConfigUnknownKeyTypeError, e.__class__
                )
                self.assertTrue("Unknown type" in str(e))
            # Set Get not defined type
            config.test3 = "abc"
            self.assertEqual(config.test3, "abc")
            config.test3 = True
            self.assertTrue(config.test3)

            # Test deleter
            # Normal option
            del config.test2
            # Non set option
            del config.test2
            # Unknown type option
            try:
                del config.test
            except Exception as e:
                self.assertEqual(
                    utils_config.LibvirtConfigUnknownKeyTypeError, e.__class__
                )
                self.assertTrue("Unknown type" in str(e))
            # Not defined option
            try:
                del config.test3
            except Exception as e:
                self.assertEqual(utils_config.LibvirtConfigUnknownKeyError, e.__class__)
                self.assertTrue("Unknown config key" in str(e))

            config.restore()
        finally:
            os.remove("/tmp/config_unittest.conf")


class LibvirtConfigTest(unittest.TestCase):
    def test_accessers(self):
        config_file = tempfile.NamedTemporaryFile()
        config_path = config_file.name
        config_file.close()
        try:
            config_file = open(config_path, "w")
            config_file.write("")
            config_file.close()
            config = utils_config.LibvirtdConfig(path=config_path)

            # Test internal property.
            self.assertEqual(config.conf_path, config_path)

            # Test undefined property.
            try:
                config.undefined_property
            except Exception as e:
                self.assertEqual(utils_config.LibvirtConfigUnknownKeyError, e.__class__)
                self.assertTrue("Unknown config key" in str(e))

            # Test defined boolean property.
            self.assertEqual(config.listen_tls, None)
            config.listen_tls = 1
            self.assertEqual(config.get_raw("listen_tls"), "1")
            self.assertEqual(config.listen_tls, 1)
            config.listen_tls = False
            self.assertEqual(config.get_raw("listen_tls"), "0")
            self.assertEqual(config.listen_tls, 0)
            config.listen_tls = "1"
            self.assertEqual(config.get_raw("listen_tls"), "1")
            config.listen_tls = "undefined"
            self.assertEqual(config.get_raw("listen_tls"), "undefined")
            del config.listen_tls
            self.assertEqual(config.listen_tls, None)

            # Test defined string property.
            self.assertEqual(config.host_uuid, None)
            config.host_uuid = 1
            self.assertEqual(config.get_raw("host_uuid"), '"1"')
            config.host_uuid = "a"
            self.assertEqual(config.get_raw("host_uuid"), '"a"')

            # Test defined integer property.
            self.assertEqual(config.max_clients, None)
            config.max_clients = 1
            self.assertEqual(config.get_raw("max_clients"), "1")

            # Test defined list property.
            self.assertEqual(config.access_drivers, None)
            config.access_drivers = [1, "a"]
            self.assertEqual(config.get_raw("access_drivers"), '["1", "a"]')
        finally:
            os.remove(config_path)


if __name__ == "__main__":
    unittest.main()
