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

import logging
import os
import shutil

# pylint: disable=E0611
from avocado_vt.agent.app.args import init_arguments
from avocado_vt.agent.app.cmd import run
from avocado_vt.agent.core import data_dir as core_data_dir
from avocado_vt.agent.core.logger import DEFAULT_LOG_NAME, init_logger


def cleanup_previous_run(dirs):
    """
    Clean up directories from previous agent runs.

    :param dirs: Tuple of directory paths to clean up
    :type dirs: tuple
    """
    for directory in dirs:
        if os.path.exists(directory):
            try:
                shutil.rmtree(directory)
            except OSError:
                pass


def setup_directories(dirs, logger):
    """
    Create necessary directories for agent operation.

    :param dirs: Tuple of directory paths to create
    :type dirs: tuple
    :param logger: Logger instance for reporting
    :type logger: logging.Logger
    """
    for directory in dirs:
        try:
            os.makedirs(directory, exist_ok=True)
        except OSError as e:
            logger.error("Failed to create directory %s: %s", directory, e)
            raise


def main():
    """Main entry point for the agent."""
    args = init_arguments()

    data_dir = core_data_dir.get_data_dir()
    log_dir = core_data_dir.get_log_dir()
    download_dir = core_data_dir.get_download_dir()
    dirs = (data_dir, log_dir, download_dir)

    cleanup_previous_run(dirs)

    init_logger()
    logger = logging.getLogger(f"{DEFAULT_LOG_NAME}.__main__")

    setup_directories(dirs, logger)

    run(args.host, args.port, args.pid_file)


if __name__ == "__main__":
    main()
