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

import os
import sys


def insert_dirs_to_path(dirs):
    """Insert directories into the Python path.

    This is used so that tests from other providers can be loaded.

    :param dirs: directories to be added to the Python path
    :type dirs: list
    """
    for directory in dirs:
        if os.path.dirname(directory) not in sys.path:
            sys.path.insert(0, os.path.dirname(directory))
