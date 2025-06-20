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
# Copyright: Red Hat Inc. 2025
# Authors: Yongxue Hong <yhong@redhat.com>

import os
import shutil

from .app.args import init_arguments
from .app.cmd import run
from .core.logger import init_logger
from .core import data_dir as core_data_dir

args = init_arguments()
data_dir = core_data_dir.get_data_dir()
log_dir = core_data_dir.get_log_dir()
download_dir = core_data_dir.get_download_dir()
console_log_dir = core_data_dir.get_console_log_dir()
daemon_log_dir = core_data_dir.get_daemon_log_dir()

dirs = (data_dir, log_dir, download_dir, console_log_dir, daemon_log_dir)

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
