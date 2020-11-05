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

import sys

# pylint: disable=E0611
from setuptools import setup, find_packages

VERSION = open('VERSION', 'r').read().strip()


def pre_post_plugin_type():
    try:
        from avocado.core.plugin_interfaces import JobPreTests as Pre
        return 'avocado.plugins.result_events'
    except ImportError:
        return 'avocado.plugins.job.prepost'


if __name__ == "__main__":
    requirements = ["netifaces", "simplejson", "six"]
    if sys.version_info[:2] >= (3, 0):
        requirements.append("avocado-framework>=68.0")
        requirements.append("netaddr")
        requirements.append("aexpect")
    else:
        # Latest py2 supported stevedore is 1.10.0, need to limit it here
        # as older avocado versions were not limiting it.
        # Note: Avocado 70+ doesn't require stevedore and older Avocado
        # can use whatever version of stevedore on py3
        requirements.append("aexpect<=1.6.0")
        requirements.append("urllib3<=1.24.3")
        requirements.append("stevedore>=1.8.0,<=1.10.0")
        requirements.append("avocado-framework>=68.0,<70.0")
        requirements.append("netaddr<=0.7.19")

    setup(name='avocado-framework-plugin-vt',
          version=VERSION,
          description='Avocado Plugin for Virtualization Testing',
          author='Avocado Developers',
          author_email='avocado-devel@redhat.com',
          url='http://github.com/avocado-framework/avocado-vt',
          packages=find_packages(exclude=('selftests*',)),
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
              'avocado.plugins.init': [
                  'vt-init = avocado_vt.plugins.vt_init:VtInit',
                  ],
              },
          install_requires=requirements,
          )
