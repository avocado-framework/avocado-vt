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
import logging.handlers
import os
import sys

# pylint: disable=E0611
from avocado_vt.agent.core import data_dir

DEFAULT_LOG_NAME = "avocado.agent"
DEFAULT_LOG_FORMAT = "%(asctime)s %(name)s %(levelname)-5.5s| %(message)s"
DEFAULT_LOG_LEVEL = logging.DEBUG
DEFAULT_CONSOLE_LEVEL = logging.INFO
DEFAULT_FILE_LEVEL = logging.DEBUG

MAX_LOG_FILE_SIZE = 10 * 1024 * 1024
LOG_BACKUP_COUNT = 5


def _validate_log_level(level):
    """
    Validate and convert log level to logging constant.

    :param level: Log level as string or int
    :type level: str or int
    :return: Validated log level
    :rtype: int
    :raises ValueError: If log level is invalid
    """
    if isinstance(level, int):
        if level in [
            logging.DEBUG,
            logging.INFO,
            logging.WARNING,
            logging.ERROR,
            logging.CRITICAL,
        ]:
            return level
        else:
            raise ValueError(f"Invalid numeric log level: {level}")

    if isinstance(level, str):
        level_map = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "WARN": logging.WARNING,
            "ERROR": logging.ERROR,
            "CRITICAL": logging.CRITICAL,
            "FATAL": logging.CRITICAL,
        }
        level_upper = level.upper()
        if level_upper in level_map:
            return level_map[level_upper]
        else:
            raise ValueError(f"Invalid log level string: {level}")

    raise ValueError(f"Log level must be string or int, got: {type(level)}")


def _create_file_handler(
    log_file, level=DEFAULT_FILE_LEVEL, format_str=DEFAULT_LOG_FORMAT
):
    """
    Create a rotating file handler for logging.

    :param log_file: Path to the log file
    :type log_file: str
    :param level: Log level for the file handler
    :type level: int
    :param format_str: Log format string
    :type format_str: str
    :return: Configured file handler
    :rtype: logging.handlers.RotatingFileHandler
    :raises OSError: If log file cannot be created
    """
    log_dir = os.path.dirname(log_file)
    if not os.path.exists(log_dir):
        try:
            os.makedirs(log_dir, exist_ok=True)
        except OSError as e:
            raise OSError(f"Cannot create log directory {log_dir}: {e}") from e

    if not os.access(log_dir, os.W_OK):
        raise OSError(f"Log directory is not writable: {log_dir}")

    try:
        file_handler = logging.handlers.RotatingFileHandler(
            filename=log_file,
            maxBytes=MAX_LOG_FILE_SIZE,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(logging.Formatter(fmt=format_str))
        return file_handler
    except OSError as e:
        raise OSError(f"Cannot create log file handler for {log_file}: {e}") from e


def _create_console_handler(level=DEFAULT_CONSOLE_LEVEL, format_str=DEFAULT_LOG_FORMAT):
    """
    Create a console handler for logging.

    :param level: Log level for the console handler
    :type level: int
    :param format_str: Log format string
    :type format_str: str
    :return: Configured console handler
    :rtype: logging.StreamHandler
    """
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(logging.Formatter(fmt=format_str))
    return console_handler


def init_logger(console_level=None, file_level=None, log_format=None):
    """
    Initialize the agent logger with enhanced configuration options.

    Sets up a logger named $DEFAULT_LOG_NAME with both console and file output.
    Uses rotating file handler to manage log file size and provides configurable
    log levels for different outputs.

    :param console_level: Log level for console output (default: INFO)
    :type console_level: str or int or None
    :param file_level: Log level for file output (default: DEBUG)
    :type file_level: str or int or None
    :param log_format: Custom log format string (default: standard format)
    :type log_format: str or None
    :return: The configured logger object
    :rtype: logging.Logger
    :raises ValueError: If log levels are invalid
    :raises OSError: If log file cannot be created
    """
    console_level = (
        _validate_log_level(console_level) if console_level else DEFAULT_CONSOLE_LEVEL
    )
    file_level = _validate_log_level(file_level) if file_level else DEFAULT_FILE_LEVEL
    log_format = log_format if log_format else DEFAULT_LOG_FORMAT

    logger = logging.getLogger(DEFAULT_LOG_NAME)
    if logger.hasHandlers():
        logger.handlers.clear()

    logger.setLevel(min(console_level, file_level))

    try:
        console_handler = _create_console_handler(console_level, log_format)
        logger.addHandler(console_handler)

        file_handler = _create_file_handler(
            data_dir.AGENT_LOG_FILENAME, file_level, log_format
        )
        logger.addHandler(file_handler)

        return logger

    except (OSError, PermissionError, ValueError) as e:
        print(f"Warning: Failed to initialize file logging: {e}", file=sys.stderr)
        print("Falling back to console-only logging", file=sys.stderr)

        logger.handlers.clear()
        console_handler = _create_console_handler(console_level, log_format)
        logger.addHandler(console_handler)
        logger.setLevel(console_level)

        logger.warning("File logging disabled due to initialization failure: %s", e)
        return logger
