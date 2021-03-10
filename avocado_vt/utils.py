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
import sys

from avocado.core import exceptions

from virttest import asset
from virttest import data_dir


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
    """Find directories containining subtests.

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
