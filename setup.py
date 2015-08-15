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
import glob

# pylint: disable=E0611
from distutils.core import setup

VERSION = '0.27.0'

VIRTUAL_ENV = 'VIRTUAL_ENV' in os.environ


def get_dir(system_path=None, virtual_path=None):
    """
    Retrieve VIRTUAL_ENV friendly path
    :param system_path: Relative system path
    :param virtual_path: Overrides system_path for virtual_env only
    :return: VIRTUAL_ENV friendly path
    """
    if virtual_path is None:
        virtual_path = system_path
    if VIRTUAL_ENV:
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

    data_files = [(get_dir(['etc', 'avocado', 'conf.d']),
                   ['etc/avocado/conf.d/vt.conf'])]

    data_files += [(get_dir(['usr', 'share', 'avocado-plugins-vt',
                             'test-providers.d']),
                    glob.glob('test-providers.d/*'))]

    data_files_dirs = ['backends', 'shared']

    for data_file_dir in data_files_dirs:
        for root, dirs, files in os.walk(data_file_dir):
            for subdir in dirs:
                rt = root.split('/')
                rt.append(subdir)
                data_files += add_files(rt)

    return data_files

setup(name='avocado-plugins-vt',
      version=VERSION,
      description='Avocado Virt Test Compatibility Layer plugin',
      author='Lucas Meneghel Rodrigues',
      author_email='lmr@redhat.com',
      url='http://github.com/avocado-framework/avocado-vt',
      packages=['avocado',
                'avocado.core.plugins',
                'virttest',
                'virttest.libvirt_xml',
                'virttest.libvirt_xml.devices',
                'virttest.libvirt_xml.nwfilter_protocols',
                'virttest.qemu_devices',
                'virttest.remote_commander',
                'virttest.staging',
                'virttest.staging.backports',
                'virttest.tests',
                'virttest.unittest_utils',
                'virttest.utils_test'],
      data_files=get_data_files()
      )
