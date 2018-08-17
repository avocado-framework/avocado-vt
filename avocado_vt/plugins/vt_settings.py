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
# Copyright: Red Hat Inc. 2018
# Author: Lukas Doktor <ldoktor@redhat.com>

"""
Avocado plugin that extends the settings path of our config paths
"""

import os
from pkg_resources import resource_filename
from pkg_resources import resource_listdir

from avocado.core.plugin_interfaces import Settings


class VTSettings(Settings):

    def adjust_settings_paths(self, paths):
        base = resource_filename('avocado_vt', 'conf.d')
        for path in [os.path.join(base, conf)
                     for conf in resource_listdir('avocado_vt', 'conf.d')
                     if conf.endswith('.conf')]:
            paths.insert(0, path)
