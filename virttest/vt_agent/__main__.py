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
# Copyright: Red Hat Inc. 2022
# Authors: Yongxue Hong <yhong@redhat.com>

"""
Main entry point when called by 'python -m'.
"""

import os
import shutil

from . import LOG_DIR
from .app.cmd import run
from .app.args import init_arguments
from .core.logger import init_logger

args = init_arguments()

try:
    shutil.rmtree(LOG_DIR)
    os.remove(args.pid_file)
except (FileNotFoundError, OSError):
    pass

os.makedirs(LOG_DIR)

root_logger = init_logger()

if __name__ == '__main__':
    run(args.host, args.port, args.pid_file)
