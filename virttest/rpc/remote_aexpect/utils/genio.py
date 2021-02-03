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

"""
Naive module that keeps tacks of some opened files and somehow manages them.
"""

import os

# This variable is used from Avocado-vt
_open_log_files = {}    # pylint: disable=C0103


def close_log_file(filename):

    """
    This closes all files that use the same "filename" (not just path, but
    really just "basename(filename)".
    """

    remove = []
    for log_file in _open_log_files:
        if os.path.basename(log_file) == filename:
            log_fd = _open_log_files[log_file]
            log_fd.close()
            remove.append(log_file)
    if remove:
        for key_to_remove in remove:
            _open_log_files.pop(key_to_remove)
