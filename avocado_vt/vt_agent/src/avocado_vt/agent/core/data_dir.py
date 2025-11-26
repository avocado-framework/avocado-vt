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
import stat
import tempfile

# pylint: disable=E0611
from avocado_vt.agent.core.logger import DEFAULT_LOG_NAME

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
LOG_DIR = os.path.join(DATA_DIR, "log")
DOWNLOAD_DIR = os.path.join(DATA_DIR, "download")

CONSOLE_LOG_DIR = os.path.join(LOG_DIR, "console")
DAEMON_LOG_DIR = os.path.join(LOG_DIR, "daemon")
IP_SNIFFER_DIR = os.path.join(DATA_DIR, "ip_sniffer")

AGENT_LOG_FILENAME = os.path.join(LOG_DIR, "agent.log")
SERVICE_LOG_FILENAME = os.path.join(LOG_DIR, "service.log")
JOB_DATA_DIR = os.path.join(DATA_DIR, "job_data")


LOG = logging.getLogger(f"{DEFAULT_LOG_NAME}." + __name__)


def get_root_dir():
    """
    Gets the root directory of the agent.

    :return: The absolute path to the agent's root directory.
    :rtype: str
    """
    return BASE_DIR


def get_data_dir():
    """
    Gets the main data directory for the agent.

    :return: The absolute path to the data directory.
    :rtype: str
    """
    return DATA_DIR


def get_log_dir():
    """
    Gets the directory where log files are stored.

    :return: The absolute path to the log directory.
    :rtype: str
    """
    return LOG_DIR


def get_download_dir():
    """
    Gets the directory where downloaded files are stored.

    :return: The absolute path to the download directory.
    :rtype: str
    """
    return DOWNLOAD_DIR


def get_job_data_dir():
    """
    Gets the directory where job-specific data is stored.

    :return: The absolute path to the job data directory.
    :rtype: str
    """
    return JOB_DATA_DIR


def get_console_log_dir():
    """
    Gets the directory where console log files are stored.

    :return: The absolute path to the console log directory.
    :rtype: str
    """
    return CONSOLE_LOG_DIR


def get_daemon_log_dir():
    """
    Gets the directory where daemon log files are stored.

    :return: The absolute path to the daemon log directory.
    :rtype: str
    """
    return DAEMON_LOG_DIR


def get_ip_sniffer_log_dir():
    """
    Gets the directory where IP sniffer data files are stored.

    :return: The absolute path to the IP sniffer directory.
    :rtype: str
    """
    return IP_SNIFFER_DIR


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
    if not os.path.exists(data_dir_path):
        try:
            os.makedirs(data_dir_path)
        except OSError as e:
            LOG.error(
                "Failed to create data directory %s for temp dir: %s", data_dir_path, e
            )
            raise

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
            LOG.warning(
                "Failed to set public permissions on tmp_dir %s: %s", tmp_dir, e
            )
    return tmp_dir


def get_services_module_dir():
    """
    Gets the directory containing the agent's service modules.

    :return: The absolute path to the services module directory.
    :rtype: str
    """
    return os.path.join(get_root_dir(), "services")


if __name__ == "__main__":
    print("base dir:         " + get_root_dir())
    print("data dir:         " + get_data_dir())
    print("log dir:         " + get_log_dir())
    print("services module dir:         " + get_services_module_dir())
    print("download dir:         " + get_download_dir())
    print("job data log dir:         " + get_job_data_dir())
    print("tmp dir:          " + get_tmp_dir())
