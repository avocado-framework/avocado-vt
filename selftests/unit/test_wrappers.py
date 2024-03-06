import os
import random
import sys
import unittest
from abc import ABC
from concurrent.futures import ThreadPoolExecutor, wait
from copy import deepcopy
from string import ascii_lowercase as ascii_lc
from time import sleep

from virttest import _wrappers


def create_module(name, inner_val, path=""):
    """Creates a module with a variable in it named inner_variable whose
    value is equal to the one set
    :param name: name of the module
    :type name: String
    :param inner_val: value that will be assigned to inner_variable
    :type inner_val: Int
    :param path: path to the module
    :type path: String
    """
    module_code = (
        """# This is a file created during virttest._wrappers tests
# This file should be deleted once the tests are finished
inner_variable = %s
"""
        % inner_val
    )
    if path != "" and not os.path.isdir(path):
        os.makedirs(path)
    with open(os.path.join(path, f"{name}.py"), "w") as new_module:
        new_module.write(module_code)


def check_imported_module(testcase, name, module, value):
    """Wraps general checks that are repeated across almost all tests."""
    testcase.assertIsNotNone(module)
    testcase.assertEqual(module.inner_variable, value)
    testcase.assertTrue(module in sys.modules.values())
    testcase.assertTrue(module is sys.modules[name])


class baseImportTests(ABC):
    _tmp_in_module_name = "tmp_module_in"
    _tmp_sub_module_name = "tmp_module_sub"
    _tmp_sub_module_dir = "_wrappers_tests_mods"
    _aux_sub_mod_dir = "_wrappers_aux_test_mods"
    _subdir_inner_val = 1
    _indir_inner_val = 0

    @classmethod
    def setUpClass(cls):
        create_module(cls._tmp_in_module_name, cls._indir_inner_val)
        create_module(
            cls._tmp_sub_module_name, cls._subdir_inner_val, cls._tmp_sub_module_dir
        )
        os.makedirs(cls._aux_sub_mod_dir)
        # Wait a bit so the import mechanism cache can be refreshed
        sleep(2)

    @classmethod
    def tearDownClass(cls):
        def rm_subdir(subdir):
            # Remove inner __pycache__
            sub_pycache_dir = os.path.join(subdir, "__pycache__")
            if os.path.exists(sub_pycache_dir):
                for pycache_file in os.listdir(sub_pycache_dir):
                    os.remove(os.path.join(sub_pycache_dir, pycache_file))
                os.rmdir(sub_pycache_dir)
            # Remove sub-module files
            for tmp_sub_mod in os.listdir(subdir):
                os.remove(os.path.join(subdir, tmp_sub_mod))
            # Finally delete created directory
            os.rmdir(subdir)

        rm_subdir(cls._tmp_sub_module_dir)
        rm_subdir(cls._aux_sub_mod_dir)
        # And the file created in the exec dir
        os.remove(f"{cls._tmp_in_module_name}.py")

    def _compare_mods(self, one, other):
        self.assertEqual(one.__name__, other.__name__)
        self.assertEqual(one.__spec__.origin, other.__spec__.origin)

    def test_import_from_subdir(self):
        """Imports a module that's in another directory"""
        pre_sys_path = deepcopy(sys.path)
        self._check_import(
            self._tmp_sub_module_name, self._subdir_inner_val, self._tmp_sub_module_dir
        )
        self.assertEqual(pre_sys_path, sys.path)

    def test_import_just_created(self):
        """Creates modules repeatedly and checks it can import them
        without waiting any time
        """
        n_repeats = 10
        for i in range(n_repeats):
            mod_name = f"tmp_rep_mod_{i}"
            # Create module
            create_module(mod_name, i, self._tmp_sub_module_dir)
            # Import and check
            self._check_import(mod_name, i, self._tmp_sub_module_dir)

    def test_import_from_dir(self):
        """Imports a module that's in the same directory"""
        pre_sys_path = deepcopy(sys.path)
        self._check_import(self._tmp_in_module_name, self._indir_inner_val)
        self.assertEqual(pre_sys_path, sys.path)


class ImportModuleTest(baseImportTests, unittest.TestCase):
    def _check_import(self, name, value, path=""):
        """Wraps the import checking workflow used in some tests"""
        module = _wrappers.import_module(name, path)
        check_imported_module(self, name, module, value)

    def test_import_from_pythonpath(self):
        """Imports a module that's in the python path"""
        # Import os which is also being used in the other tests
        module = _wrappers.import_module("os")
        self.assertIsNotNone(module)
        self._compare_mods(module, os)

    def test_import_from_builtins(self):
        """Imports a module that's in the python path"""
        # Import os which is also being used in the other tests
        import pwd

        module = _wrappers.import_module("pwd")
        self.assertIsNotNone(module)
        self._compare_mods(module, pwd)

    def test_thread_safety(self):
        """Create 5 pairs of modules. Each pair consists of two equally named
        files with a different inner value, and saved in different
        directories.
        """

        def check_routine(module_check_data):
            module = _wrappers.import_module(
                module_check_data["name"], module_check_data["path"]
            )
            val = module.inner_variable
            return val

        def check(module_val, module_data):
            self.assertEqual(module_val, module_data["value"])

        def get_random_name(length=20):
            return "".join([random.choice(ascii_lc) for _ in range(length)])

        check_mod_names = [get_random_name() for _ in range(50)]
        check_import_data = []
        for mod_name in check_mod_names:
            value = random.randint(0, 100)
            create_module(mod_name, value, self._aux_sub_mod_dir)
            in_dir = {"name": mod_name, "value": value, "path": self._aux_sub_mod_dir}
            value = random.randint(0, 100)
            create_module(mod_name, value, self._tmp_sub_module_dir)
            sub_dir = {
                "name": mod_name,
                "value": value,
                "path": self._tmp_sub_module_dir,
            }
            # We don't want to test if two modules with the same name
            # are imported safely in the same execution.
            # We want to test that sys.path priorities are not mixed up
            # So select only one
            check_import_data.append(random.choice([in_dir, sub_dir]))
        results = []
        with ThreadPoolExecutor(max_workers=len(check_mod_names)) as executor:
            for mod_data in check_import_data:
                results.append(executor.submit(check_routine, mod_data))
        wait(results)
        for res, mod_data in zip(results, check_import_data):
            check(res.result(), mod_data)


class LoadSourceTest(baseImportTests, unittest.TestCase):
    def _check_import(self, name, value, path=""):
        path = os.path.join(path, f"{name}.py")
        module = _wrappers.load_source(name, path)
        check_imported_module(self, name, module, value)

    def test_mismatching_names(self):
        # test that importing a module mismatching the file name works good
        module = _wrappers.load_source("name", f"{self._tmp_in_module_name}.py")
        check_imported_module(self, "name", module, self._indir_inner_val)

    def test_no_existing_file(self):
        # Assert an error is launched if a non existing file is imported
        with self.assertRaises(FileNotFoundError):
            self._check_import("os", None, "os.py")
