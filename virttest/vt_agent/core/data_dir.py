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
import logging
import os
import shutil
import stat
import tempfile

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
LOG_DIR = os.path.join(DATA_DIR, "log")
DOWNLOAD_DIR = os.path.join(DATA_DIR, "download")
CONSOLE_LOG_DIR = os.path.join(LOG_DIR, "console")
DAEMON_LOG_DIR = os.path.join(LOG_DIR, "daemon")
IP_SNIFFER_DIR = os.path.join(DATA_DIR, "ip_sniffer")

AGENT_LOG_FILENAME = os.path.join(LOG_DIR, "agent.log")
SERVICE_LOG_FILENAME = os.path.join(LOG_DIR, "service.log")
BACKING_MGR_ENV_FILENAME = os.path.join(DATA_DIR, "backing_mgr.env")


LOG = logging.getLogger("avocado.agent" + __name__)


def get_root_dir():
    return BASE_DIR


def get_data_dir():
    return DATA_DIR


def get_log_dir():
    return LOG_DIR


def get_console_log_dir():
    return CONSOLE_LOG_DIR


def get_daemon_log_dir():
    return DAEMON_LOG_DIR


def get_ip_sniffer_log_dir():
    return IP_SNIFFER_DIR


def get_download_dir():
    return DOWNLOAD_DIR


def get_tmp_dir(public=True):
    """
    Get the most appropriate tmp dir location.
    This creates a new temporary directory with prefix "agent_tmp_"
    inside the directory returned by get_data_dir().

    :param public: If public for all users' access (sets permissions)
    :type public: bool
    :return: The path to the created temporary directory.
    :rtype: str
    """
    data_dir_path = get_data_dir()
    # Ensure data_dir_path itself exists, as mkdtemp might not create it.
    # This should be handled by __main__.py, but a check here adds robustness.
    if not os.path.exists(data_dir_path):
        try:
            os.makedirs(data_dir_path)
        except OSError as e:
            LOG.error("Failed to create data directory %s for temp dir: %s",
                      data_dir_path, e)
            # Potentially raise an error or return a fallback like /tmp
            raise  # Re-raise if data_dir cannot be created, as it's fundamental

    tmp_dir = tempfile.mkdtemp(prefix="agent_tmp_", dir=data_dir_path)
    if public:
        try:
            tmp_dir_st = os.stat(tmp_dir)
            os.chmod(
                tmp_dir,
                tmp_dir_st.st_mode
                | stat.S_IXUSR
                | stat.S_IXGRP
                | stat.S_IXOTH
                | stat.S_IRGRP
                | stat.S_IROTH,
            )
        except OSError as e:
            LOG.warning("Failed to set public permissions on tmp_dir %s: %s",
                        tmp_dir, e)
    return tmp_dir


def get_services_module_dir():
    return os.path.join(get_root_dir(), "services")


def get_managers_module_dir():
    return os.path.join(get_root_dir(), "managers")


def clean_tmp_files():
    tmp_dir = get_tmp_dir()
    if os.path.isdir(tmp_dir):
        hidden_paths = glob.glob(os.path.join(tmp_dir, ".??*"))
        paths = glob.glob(os.path.join(tmp_dir, "*"))
        for path in paths + hidden_paths:
            shutil.rmtree(path, ignore_errors=True)


if __name__ == "__main__":
    print("base dir:         " + get_root_dir())
    print("data dir:         " + get_data_dir())
    print("log dir:         " + get_log_dir())
    print("services module dir:         " + get_services_module_dir())
    print("managers module dir:         " + get_managers_module_dir())
    print("download dir:         " + get_download_dir())
    print("tmp dir:          " + get_tmp_dir())
    print("console log dir:         " + get_console_log_dir())
    print("daemon log dir:         " + get_daemon_log_dir())
