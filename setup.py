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

import os
import sys
import glob

# pylint: disable=E0611
from setuptools import setup, find_packages

VERSION = open('VERSION', 'r').read().strip()


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

    data_files = add_files(["test-providers.d"])
    data_files_dirs = ['backends', 'shared']

    for data_file_dir in data_files_dirs:
        for root, dirs, files in os.walk(data_file_dir):
            for subdir in dirs:
                rt = root.split('/')
                rt.append(subdir)
                data_files += add_files(rt)

    return data_files


def pre_post_plugin_type():
    try:
        from avocado.core.plugin_interfaces import JobPreTests as Pre
        return 'avocado.plugins.result_events'
    except ImportError:
        return 'avocado.plugins.job.prepost'


if __name__ == "__main__":
    requirements = ["netifaces", "aexpect", "netaddr", "simplejson", "six"]
    if sys.version_info[:2] >= (2, 7):
        requirements.append("avocado-framework>=68.0")
    else:
        # Latest py2 supported stevedore is 1.10.0, need to limit it here
        # as older avocado versions were not limiting it.
        # Note: Avocado 70+ doesn't require stevedore and older Avocado
        # can use whatever version of stevedore on py3
        requirements.append("stevedore>=1.8.0,<=1.10.0")
        requirements.append("avocado-framework>=68.0,<70.0")

    setup(name='avocado-framework-plugins-vt',
          version=VERSION,
          description='Avocado Plugin for Virtualization Testing',
          author='Avocado Developers',
          author_email='avocado-devel@redhat.com',
          url='http://github.com/avocado-framework/avocado-vt',
          packages=find_packages(exclude=('selftests*',)),
          package_data={"virttest": ["*.*"]},
          data_files=get_data_files(),
          include_package_data=True,
          entry_points={
              'avocado.plugins.settings': [
                  'vt-settings = avocado_vt.plugins.vt_settings:VTSettings',
                  ],
              'avocado.plugins.cli': [
                  'vt-list = avocado_vt.plugins.vt_list:VTLister',
                  'vt = avocado_vt.plugins.vt:VTRun',
                  ],
              'avocado.plugins.cli.cmd': [
                  'vt-bootstrap = avocado_vt.plugins.vt_bootstrap:VTBootstrap',
                  ],
              pre_post_plugin_type(): [
                  'vt-joblock = avocado_vt.plugins.vt_joblock:VTJobLock',
                  ],
              },
          install_requires=requirements,
          )
