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
# Copyright: Red Hat Inc. 2013-2014
# Author: Lucas Meneghel Rodrigues <lmr@redhat.com>

# pylint: disable=E0611

import os
import sys
import glob
from setuptools import find_packages, setup

VERSION = open("VERSION", "r").read().strip()


def __is_virtual_env():
    return (hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and
                                            sys.base_prefix != sys.prefix))


def get_dir(system_path=None, virtual_path=None):
    """
    Retrieve VIRTUAL_ENV friendly path
    :param system_path: Relative system path
    :param virtual_path: Overrides system_path for virtual_env only
    :return: VIRTUAL_ENV friendly path
    """
    if virtual_path is None:
        virtual_path = system_path
    if __is_virtual_env():
        if virtual_path is None:
            virtual_path = []
        return os.path.join(*virtual_path)
    else:
        if system_path is None:
            system_path = []
        return os.path.join(*(['/'] + system_path))


def get_data_files():
    def add_files(level=[]):
        installed_location = ['usr', 'share', 'avocado-plugins-vt']
        installed_location += level
        level_str = '/'.join(level)
        if level_str:
            level_str += '/'
        file_glob = '%s*' % level_str
        files_found = [path for path in glob.glob(file_glob) if
                       os.path.isfile(path)]
        return [((get_dir(installed_location, level)), files_found)]

    data_files = []
    data_files_dirs = ['tp_folder']

    for data_file_dir in data_files_dirs:
        for root, dirs, files in os.walk(data_file_dir):
            for subdir in dirs:
                rt = root.split('/')
                rt.append(subdir)
                data_files += add_files(rt)

    return data_files


if __name__ == "__main__":
    setup(
        name="avocado-framework-plugin-vt",
        version=VERSION,
        description="Avocado Plugin for Virtualization Testing",
        author="Avocado Developers",
        author_email="avocado-devel@redhat.com",
        url="http://github.com/avocado-framework/avocado-vt",
        packages=find_packages(exclude=("selftests*",)),
        include_package_data=True,
        package_data={
            "avocado_vt": ["conf.d/**"],
            "virttest": [
                "test-providers.d/**",
                "backends/**",
                "shared/**",
            ],
            'virttest.vmnet': ['templates/*.template']
        },
        install_requires=[
            "packaging",
            "six",
            "aexpect",
            "avocado-framework>=82.1",
        ],
        data_files=get_data_files(),
        entry_points={
            "console_scripts": [
                "avocado-runner-avocado-vt = avocado_vt.plugins.vt_runner:main",
            ],
            "avocado.plugins.settings": [
                "vt-settings = avocado_vt.plugins.vt_settings:VTSettings",
            ],
            "avocado.plugins.cli": [
                "vt-list = avocado_vt.plugins.vt_list:VTLister",
                "vt = avocado_vt.plugins.vt:VTRun",
                'auto = avocado_vt.plugins.auto:Auto',
            ],
            "avocado.plugins.cli.cmd": [
                "vt-bootstrap = avocado_vt.plugins.vt_bootstrap:VTBootstrap",
                "vt-list-guests = avocado_vt.plugins.vt_list_guests:VTListGuests",
                "vt-list-archs = avocado_vt.plugins.vt_list_archs:VTListArchs",
                'manu = avocado_vt.plugins.manu:Manu',
            ],
            "avocado.plugins.result_events": [
                "vt-joblock = avocado_vt.plugins.vt_joblock:VTJobLock",
                "vt-cluster = avocado_vt.plugins.vt_cluster:VTCluster",
            ],
            "avocado.plugins.init": [
                "vt-init = avocado_vt.plugins.vt_init:VtInit",
            ],
            "avocado.plugins.resolver": [
                "avocado-vt = avocado_vt.plugins.vt_resolver:VTResolver",
                'parser = avocado_vt.plugins.loader:TestLoader',
            ],
            "avocado.plugins.discoverer": [
                "avocado-vt = avocado_vt.plugins.vt_resolver:VTDiscoverer"
            ],
            "avocado.plugins.runnable.runner": [
                "avocado-vt = avocado_vt.plugins.vt_runner:VTTestRunner",
            ],
            "avocado.plugins.suite.runner": [
                "traverser = avocado_vt.plugins.runner:TestRunner",
            ],
        },
    )
