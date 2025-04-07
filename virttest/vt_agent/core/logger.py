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

import logging.handlers

from .data_dir import AGENT_LOG_FILENAME

LOG_FORMAT = "%(asctime)s %(name)s %(levelname)-5.5s| %(message)s"


def init_logger():
    """
    Initialize the agent logger client.

    :return: The logger client obj.
    :rtype: logging.Logger
    """
    logger = logging.getLogger("avocado.agent")
    logger.setLevel(logging.DEBUG)

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.DEBUG)
    stream_handler.setFormatter(logging.Formatter(fmt=LOG_FORMAT))
    logger.addHandler(stream_handler)

    file_handler = logging.FileHandler(filename=AGENT_LOG_FILENAME)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(fmt=LOG_FORMAT))
    logger.addHandler(file_handler)

    return logger
