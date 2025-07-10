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

import glob
import logging.handlers
import os
import shutil
import signal

from .core import data_dir
from .core.logger import LOG_FORMAT

LOG = logging.getLogger("avocado.agent." + __name__)


def quit():
    """Quit the agent server."""
    pid = os.getpid()
    LOG.info("Requesting server daemon (PID:%s) to terminate.", pid)
    os.kill(pid, signal.SIGTERM)


def is_alive():
    """Check whether the agent server is alive."""
    LOG.info("The server daemon is alive.")
    return True


def start_logger_client(host, port):
    """Start the agent logger client"""
    try:
        os.remove(data_dir.SERVICE_LOG_FILENAME)
    except FileNotFoundError:
        pass

    # Configure avocado.service logger
    svc_logger = logging.getLogger("avocado.service")
    svc_logger.setLevel(logging.DEBUG)
    # Prevent adding duplicate handlers if called multiple times without stopping
    while svc_logger.hasHandlers():
        try:
            svc_logger.removeHandler(svc_logger.handlers[0])
        except IndexError:
            break

    svc_file_handler = logging.FileHandler(filename=data_dir.SERVICE_LOG_FILENAME)
    svc_file_handler.setFormatter(logging.Formatter(fmt=LOG_FORMAT))
    svc_logger.addHandler(svc_file_handler)

    # Configure avocado.virttest logger
    vt_logger = logging.getLogger("avocado.virttest")
    vt_logger.setLevel(logging.DEBUG)
    # Prevent adding duplicate handlers
    while vt_logger.hasHandlers():
        try:
            vt_logger.removeHandler(vt_logger.handlers[0])
        except IndexError:
            break

    vt_file_handler = logging.FileHandler(filename=data_dir.SERVICE_LOG_FILENAME)
    vt_file_handler.setFormatter(logging.Formatter(fmt=LOG_FORMAT))
    vt_logger.addHandler(vt_file_handler)

    LOG.info("Starting the logger client to forward to %s:%s.", host, port)
    socket_handler_svc = logging.handlers.SocketHandler(host, port)
    socket_handler_svc.setLevel(logging.DEBUG)
    svc_logger.addHandler(socket_handler_svc)

    socket_handler_vt = logging.handlers.SocketHandler(host, port)
    socket_handler_vt.setLevel(logging.DEBUG)
    vt_logger.addHandler(socket_handler_vt)
    LOG.info("Logger client started.")


def stop_logger_client():
    """Stop the agent logger client."""
    LOG.info("Stopping the logger client.")

    logger_names = ["avocado.service", "avocado.virttest"]
    for name in logger_names:
        logger = logging.getLogger(name)
        for handler in list(logger.handlers):  # Iterate over a copy
            try:
                handler.close()
            except Exception as e:
                LOG.warning(
                    "Failed to close handler %s for logger %s: %s", handler, name, e
                )
            logger.removeHandler(handler)  # Explicitly remove
    LOG.info("Logger client stopped.")


def get_agent_log_filename():
    """Get the filename of the agent log."""
    return data_dir.AGENT_LOG_FILENAME


def get_service_log_filename():
    """Get the filename of the service log."""
    return data_dir.SERVICE_LOG_FILENAME


def get_log_dir():
    """Get the filename of the logs."""
    return data_dir.get_log_dir()


def cleanup_tmp_files(file_path):
    """
    Cleanup temporary files
    """
    try:
        if os.path.isdir(file_path):
            shutil.rmtree(file_path)
        elif os.path.isfile(file_path):
            os.remove(file_path)
        else:
            files_found = glob.glob(file_path)
            if not files_found:
                return
            for item in files_found:
                if os.path.isfile(item):
                    os.remove(item)
                elif os.path.isdir(item):
                    shutil.rmtree(item)
                else:
                    LOG.warning(
                        "Item %s from glob is neither a file nor a directory.", item
                    )
    except (FileNotFoundError, OSError):
        pass
