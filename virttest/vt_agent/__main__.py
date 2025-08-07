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
# Copyright: Red Hat Inc. 2024
# Authors: Yongxue Hong <yhong@redhat.com>

"""
Main entry point when called by 'python -m'.
"""

import os
import shutil

from .app.args import init_arguments
from .app.cmd import run
from .core.data_dir import get_data_dir, get_download_dir, get_log_dir
from .core.logger import init_logger

args = init_arguments()
data_dir = get_data_dir()
log_dir = get_log_dir()
download_dir = get_download_dir()

dirs = (data_dir, log_dir, download_dir)

try:
    for _dir in dirs:
        shutil.rmtree(data_dir)
    os.remove(args.pid_file)
except (FileNotFoundError, OSError):
    pass

for _dir in dirs:
    os.makedirs(_dir)

root_logger = init_logger()

if __name__ == "__main__":
    run(args.host, args.port, args.pid_file)
