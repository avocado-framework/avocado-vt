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

import importlib.resources

from avocado.core.plugin_interfaces import Settings


class VTSettings(Settings):
    def adjust_settings_paths(self, paths):
        base = importlib.resources.files("avocado_vt").joinpath("conf.d")
        for path in base.iterdir():
            if path.is_file() and path.name.endswith(".conf"):
                paths.insert(0, str(path))
