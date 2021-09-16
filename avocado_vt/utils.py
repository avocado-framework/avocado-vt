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
#
# Copyright: Red Hat Inc. 2020
# Author: Cleber Rosa <crosa@redhat.com>

import imp
import logging
import os
import pickle
import sys
import traceback

from avocado.core import exceptions
from avocado.utils import genio, stacktrace

from virttest import asset, bootstrap
from virttest import data_dir

BG_ERR_FILE = "background-error.log"


def insert_dirs_to_path(dirs):
    """Insert directories into the Python path.

    This is used so that tests from other providers can be loaded.

    :param dirs: directories to be added to the Python path
    :type dirs: list
    """
    for directory in dirs:
        if os.path.dirname(directory) not in sys.path:
            sys.path.insert(0, os.path.dirname(directory))


def find_subtest_dirs(other_subtests_dirs, bindir, ignore_files=None):
    """Find directories containing subtests.

    :param other_subtests_dirs: space separate list of directories
    :type other_subtests_dirs: string
    :param bindir: the test's "binary directory"
    :type bindir: str
    :param ignore_files: files/dirs to ignore as possible candidates
    :type ignore_files: list or None
    """
    subtest_dirs = []
    for d in other_subtests_dirs.split():
        # If d starts with a "/" an absolute path will be assumed
        # else the relative path will be searched in the bin_dir
        subtestdir = os.path.join(bindir, d, "tests")
        if not os.path.isdir(subtestdir):
            raise exceptions.TestError("Directory %s does not "
                                       "exist" % subtestdir)
        subtest_dirs += data_dir.SubdirList(subtestdir,
                                            ignore_files)
    return subtest_dirs


def find_generic_specific_subtest_dirs(vm_type, ignore_files=None):
    """Find generic and specific directories containing subtests.

    This verifies if we have the correspondent source file.

    :param vm_type: type of test provider and thus VM (qemu, libvirt, etc)
    :type vm_type: string
    :param ignore_files: files/dirs to ignore as possible candidates
    :type ignore_files: list or None
    """
    subtest_dirs = []
    generic_subdirs = asset.get_test_provider_subdirs('generic')
    for generic_subdir in generic_subdirs:
        subtest_dirs += data_dir.SubdirList(generic_subdir,
                                            ignore_files)
    specific_subdirs = asset.get_test_provider_subdirs(vm_type)
    for specific_subdir in specific_subdirs:
        subtest_dirs += data_dir.SubdirList(specific_subdir,
                                            ignore_files)
    return subtest_dirs


def find_provider_subtest_dirs(provider, ignore_files=None):
    """Find directories containing subtests for specific providers.

    :param provider: provider name
    :type vm_type: string
    :param ignore_files: files/dirs to ignore as possible candidates
    :type ignore_files: list or None
    """
    subtests_dirs = []
    provider_info = asset.get_test_provider_info(provider)
    for key in provider_info['backends']:
        subtests_dirs += data_dir.SubdirList(
            provider_info['backends'][key]['path'],
            ignore_files)
    return subtests_dirs


def find_test_modules(test_types, subtest_dirs):
    """Find the test modules for given test type and dirs.

    :param test_types: the types of tests a given test sets as supported
    :type test_types: list
    :param subtests_dirs: directories possibly containing tests modules
    :type subtests_dirs: list
    """
    test_modules = {}
    for test_type in test_types:
        for d in subtest_dirs:
            module_path = os.path.join(d, "%s.py" % test_type)
            if os.path.isfile(module_path):
                logging.debug("Found subtest module %s",
                              module_path)
                subtest_dir = d
                break
        else:
            msg = ("Could not find test file %s.py on test"
                   "dirs %s" % (test_type, subtest_dirs))
            raise exceptions.TestError(msg)
        # Load the test module
        f, p, d = imp.find_module(test_type, [subtest_dir])
        test_modules[test_type] = imp.load_module(test_type, f, p, d)
        f.close()
    return test_modules


class TestUtils:

    BG_ERR_FILE = "background-error.log"

    def _safe_env_save(self, env):
        """
        Treat "env.save()" exception as warnings

        :param env: The virttest env object
        :return: True on failure
        """
        try:
            env.save()
        except Exception as details:
            try:
                pickle.dumps(env.data)
            except Exception:
                self.log.warn("Unable to save environment: %s",
                              stacktrace.str_unpickable_object(env.data))
            else:
                self.log.warn("Unable to save environment: %s (%s)", details,
                              env.data)
            return True
        return False

    def _log_parameters(self):
        """
        Report the parameters we've received and write them as keyvals
        """
        self.log.debug("Test parameters:")
        keys = list(self.params.keys())
        keys.sort()
        for key in keys:
            self.log.debug("    %s = %s", key, self.params[key])

    def _get_subtest_dirs(self):
        """
        Get list of directories containing subtests.
        """
        test_filter = bootstrap.test_filter
        subtest_dirs = find_subtest_dirs(self.params.get("other_tests_dirs",
                                                         ""),
                                         self.bindir,
                                         test_filter)
        provider = self.params.get("provider", None)

        if provider is None:
            subtest_dirs += find_generic_specific_subtest_dirs(
                self.params.get("vm_type"), test_filter)
        else:
            subtest_dirs += find_provider_subtest_dirs(provider, test_filter)
        return subtest_dirs

    def write_test_keyval(self, d):
        self.whiteboard = str(d)

    def verify_background_errors(self):
        """
        Verify if there are any errors that happened on background threads.
        Logs all errors in the background_errors into background-error.log and
        error the test.
        """
        err_file_path = os.path.join(self.logdir, BG_ERR_FILE)
        bg_errors = self.background_errors.get_all()
        error_messages = ["BACKGROUND ERROR LIST:"]
        for index, error in enumerate(bg_errors):
            error_messages.append(
                "- ERROR #%d -\n%s" % (index, "".join(
                    traceback.format_exception(*error)
                    )))
        genio.write_file(err_file_path, '\n'.join(error_messages))
        if bg_errors:
            msg = ["Background error"]
            msg.append("s are" if len(bg_errors) > 1 else " is")
            msg.append((" detected, please refer to file: "
                        "'%s' for more details.") % BG_ERR_FILE)
            self.error(''.join(msg))

    @property
    def datadir(self):
        """
        Returns the path to the directory that contains test data files

        For VT tests, this always returns None. The reason is that
        individual VT tests do not map 1:1 to a file and do not provide
        the concept of a datadir.
        """
        return None

    @property
    def filename(self):
        """
        Returns the name of the file (path) that holds the current test

        For VT tests, this always returns None. The reason is that
        individual VT tests do not map 1:1 to a file.
        """
        return None
