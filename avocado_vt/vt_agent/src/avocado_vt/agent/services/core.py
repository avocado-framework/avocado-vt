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

import json
import logging.handlers
import os
import shutil
import signal
import socket
import struct
import traceback

# pylint: disable=E0611
from avocado_vt.agent.core import data_dir
from avocado_vt.agent.core.logger import DEFAULT_LOG_FORMAT, DEFAULT_LOG_NAME

LOG = logging.getLogger(f"{DEFAULT_LOG_NAME}." + __name__)


def _log_record_to_dict(record: logging.LogRecord) -> dict:
    """
    Converts a LogRecord object to a dictionary suitable for JSON serialization.
    This dictionary can be used by `logging.makeLogRecord` on the receiving end.
    """
    msg = record.getMessage()
    record_dict = {
        "name": record.name,
        "levelno": record.levelno,
        "levelname": record.levelname,
        "pathname": record.pathname,
        "filename": record.filename,
        "module": record.module,
        "lineno": record.lineno,
        "funcName": record.funcName,
        "created": record.created,
        "asctime": record.asctime,
        "thread": record.thread,
        "threadName": record.threadName,
        "process": record.process,
        "msg": msg,
        "args": None,
    }
    if record.exc_info:
        record_dict["exc_info"] = traceback.format_exception(*record.exc_info)
    if record.stack_info:
        record_dict["stack_info"] = record.stack_info
    return record_dict


class _JSONSocketHandler(logging.Handler):
    """
    A custom logging handler that sends log records over a TCP socket as JSON.
    """

    def __init__(self, host, port):
        super().__init__()
        self.host = host
        self.port = port
        self.sock = None
        self._connect()

    def _connect(self):
        """Establish a connection to the logger server."""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(5.0)
            self.sock.connect((self.host, self.port))
        except (socket.error, ConnectionRefusedError) as e:
            LOG.error(
                f"Error connecting to logger server at {self.host}:{self.port}: {e}"
            )
            self.sock = None

    def emit(self, record: logging.LogRecord):
        """
        Converts the record to JSON and sends it to the server.
        """
        if self.sock is None:
            self._connect()
            if self.sock is None:
                return

        try:
            record_dict = _log_record_to_dict(record)
            json_data = json.dumps(record_dict).encode("utf-8")
            data_len = struct.pack(">L", len(json_data))
            self.sock.sendall(data_len + json_data)
        except (socket.error, BrokenPipeError, ConnectionResetError):
            self.sock.close()
            self.sock = None
        except (TypeError, struct.error, AttributeError) as e:
            LOG.warning(f"An unexpected error occurred in JSONSocketHandler: {e}")

    def close(self):
        """Close the socket connection."""
        if self.sock:
            self.sock.close()
        super().close()


def quit():
    """Terminates the agent server by sending a SIGTERM signal."""
    pid = os.getpid()
    LOG.info("Requesting server daemon (PID:%s) to terminate.", pid)
    os.kill(pid, signal.SIGTERM)


def is_alive():
    """Checks if the agent server is alive and responsive."""
    return True


def start_log_redirection(host, port):
    """
    Starts a logger client to forward logs to a central server.

    This function configures the 'avocado.service' and 'avocado.virttest'
    loggers to send their records to a specified host and port using a
    JSON-based socket handler. It also sets up a local file logger as a
    backup.

    :param host: The hostname or IP address of the logger server.
    :type host: str
    :param port: The port number of the logger server.
    :type port: int
    :raises ValueError: If host or port parameters are invalid
    """
    if not host or not isinstance(host, str):
        raise ValueError(f"Invalid host parameter: {host}")

    if not isinstance(port, int) or port < 1 or port > 65535:
        raise ValueError(f"Invalid port parameter: {port}")

    if any(char in host for char in [";", "&", "|", "`", "$"]):
        raise ValueError(f"Host parameter contains invalid characters: {host}")

    try:
        os.remove(data_dir.SERVICE_LOG_FILENAME)
    except FileNotFoundError:
        pass

    svc_logger = logging.getLogger("avocado.service")
    svc_logger.setLevel(logging.DEBUG)
    while svc_logger.hasHandlers():
        try:
            svc_logger.removeHandler(svc_logger.handlers[0])
        except IndexError:
            break

    svc_file_handler = logging.FileHandler(filename=data_dir.SERVICE_LOG_FILENAME)
    svc_file_handler.setFormatter(logging.Formatter(fmt=DEFAULT_LOG_FORMAT))
    svc_logger.addHandler(svc_file_handler)

    vt_logger = logging.getLogger("avocado.virttest")
    vt_logger.setLevel(logging.DEBUG)
    while vt_logger.hasHandlers():
        try:
            vt_logger.removeHandler(vt_logger.handlers[0])
        except IndexError:
            break

    vt_logger.addHandler(svc_file_handler)

    socket_handler_svc = _JSONSocketHandler(host, port)
    socket_handler_svc.setLevel(logging.DEBUG)
    svc_logger.addHandler(socket_handler_svc)

    socket_handler_vt = _JSONSocketHandler(host, port)
    socket_handler_vt.setLevel(logging.DEBUG)
    vt_logger.addHandler(socket_handler_vt)
    LOG.info("Started the logger client to forward to %s:%s.", host, port)


def stop_log_redirection():
    """Stops the logger client and closes all associated handlers."""
    logger_names = ["avocado.service", "avocado.virttest"]
    for name in logger_names:
        logger = logging.getLogger(name)
        for handler in list(logger.handlers):
            try:
                handler.close()
            except (OSError, AttributeError, ValueError) as e:
                LOG.warning(
                    "Failed to close handler %s for logger %s: %s", handler, name, e
                )
            logger.removeHandler(handler)


def get_agent_log_filename():
    """
    Gets the absolute path to the agent's main log file.

    :return: The path to the agent log file.
    :rtype: str
    """
    return data_dir.AGENT_LOG_FILENAME


def get_service_log_filename():
    """
    Gets the absolute path to the service log file.

    This log file contains logs from 'avocado.service' and
    'avocado.virttest'.

    :return: The path to the service log file.
    :rtype: str
    """
    return data_dir.SERVICE_LOG_FILENAME


def get_log_dir():
    """
    Gets the absolute path to the directory containing all logs.

    :return: The path to the log directory.
    :rtype: str
    """
    return data_dir.get_log_dir()


def get_console_log_dir():
    """Get the filename of the console logs."""
    return data_dir.get_console_log_dir()


def get_daemon_log_dir():
    """Get the filename of the daemon logs."""
    return data_dir.get_daemon_log_dir()


def get_ip_sniffer_log_dir():
    """Get the filename of the ip sniffer logs."""
    return data_dir.get_ip_sniffer_log_dir()


def get_job_data_log(job_id):
    """
    Gets the data directory for a specific job.

    :param job_id: The unique identifier for the job.
    :type job_id: str
    :return: The path to the job's data directory if it exists, otherwise None.
    :rtype: str or None
    """
    job_data_dir = os.path.join(data_dir.get_job_data_dir(), job_id, "data")
    if os.path.exists(job_data_dir):
        return job_data_dir
    return None


def get_job_results_dir(job_id):
    """
    Gets the results directory for a specific job.

    :param job_id: The unique identifier for the job.
    :type job_id: str
    :return: The path to the job's results directory if it exists,
             otherwise None.
    :rtype: str or None
    """
    job_results_dir = os.path.join(data_dir.get_job_data_dir(), job_id, "test_results")
    if os.path.exists(job_results_dir):
        return job_results_dir
    return None


def get_latest_job_results_dir():
    """
    Gets the results directory for the most recent job.

    This is determined by the 'latest' symlink in the job data directory.

    :return: The path to the latest job's results directory if it
             exists, otherwise None.
    :rtype: str or None
    """
    job_results_dir = os.path.join(
        data_dir.get_job_data_dir(), "latest", "test_results"
    )
    if os.path.exists(job_results_dir):
        return job_results_dir
    return None


def get_test_result_log_dir(suite_id, job_id=None):
    """
    Gets the result directory for a specific test suite.

    If no job_id is provided, it defaults to the latest job.

    :param suite_id: The unique identifier for the test suite.
    :type suite_id: str
    :param job_id: The job ID. Defaults to None (latest job).
    :type job_id: str or None
    :return: The path to the test suite's result directory if it
             exists, otherwise None.
    :rtype: str or None
    """
    if job_id:
        job_result_dir = get_job_results_dir(job_id)
    else:
        job_result_dir = get_latest_job_results_dir()
    if job_result_dir:
        test_result_log_dir = os.path.join(job_result_dir, suite_id)
        if os.path.exists(test_result_log_dir):
            return test_result_log_dir
        return None
    return None


def save_job_data(job_id, state_data):
    """
    Saves the state of a job and its associated logs.

    This creates a dedicated directory for the job, saves the state data to
    a JSON file, and copies the main agent log. It also creates a 'latest'
    symlink pointing to this job's directory.

    :param job_id: The unique identifier for the job.
    :type job_id: str
    :param state_data: A dictionary containing the job's state to be
                       saved as JSON.
    :type state_data: dict
    :return: True if the data was saved successfully, False otherwise.
    :rtype: bool
    """
    try:
        job_dir = os.path.join(data_dir.get_job_data_dir(), job_id)
        os.makedirs(job_dir, exist_ok=True)

        latest_dir = os.path.join(data_dir.get_job_data_dir(), "latest")
        if os.path.islink(latest_dir):
            os.unlink(latest_dir)
        os.symlink(job_dir, latest_dir, target_is_directory=True)

        test_results_dir = os.path.join(job_dir, "test_results")
        os.makedirs(test_results_dir, exist_ok=True)

        job_data_dir = os.path.join(job_dir, "data")
        os.makedirs(job_data_dir, exist_ok=True)

        state_file = os.path.join(job_data_dir, "state.json")
        with open(state_file, "w") as f:
            json.dump(state_data, f, indent=4)

        if os.path.exists(data_dir.AGENT_LOG_FILENAME):
            shutil.copy(data_dir.AGENT_LOG_FILENAME, job_data_dir)

        LOG.info("Successfully saved job data for job_id: %s", job_id)
        return True
    except (OSError, IOError, TypeError) as e:
        LOG.error("Failed to save job data for job_id %s: %s", job_id, e)
        return False


def load_job_data(job_id):
    """
    Loads the state data for a given job.

    :param job_id: The unique identifier for the job.
    :type job_id: str
    :return: The loaded state data as a dictionary, or None if
             the data cannot be loaded.
    :rtype: dict or None
    """
    try:
        job_dir = os.path.join(data_dir.get_job_data_dir(), job_id)
        state_file = os.path.join(job_dir, "state.json")
        if os.path.exists(state_file):
            with open(state_file, "r") as f:
                state_data = json.load(f)
            LOG.info("Successfully loaded job data for job_id: %s", job_id)
            return state_data
        else:
            LOG.warning("No state file found for job_id: %s", job_id)
            return None
    except (OSError, IOError, json.JSONDecodeError) as e:
        LOG.error("Failed to load job data for job_id %s: %s", job_id, e)
        return None


def delete_job_data(job_id):
    """
    Deletes the data directory for a given job.

    :param job_id: The unique identifier for the job to delete.
    :type job_id: str
    :return: True if the directory was deleted successfully, False otherwise.
    :rtype: bool
    """
    try:
        job_dir = os.path.join(data_dir.get_job_data_dir(), job_id)
        if os.path.isdir(job_dir):
            shutil.rmtree(job_dir)
            LOG.info("Successfully deleted job data for job_id: %s", job_id)
            return True
        else:
            LOG.warning("No data directory found for job_id: %s", job_id)
            return False
    except (OSError, IOError) as e:
        LOG.error("Failed to delete job data for job_id %s: %s", job_id, e)
        return False


def save_suite_data(suite_id, suite_state, suite_result, job_id=None):
    """
    Saves the state and results for a test suite.

    This creates a dedicated directory for the suite within a job's results
    directory. It saves the suite's state and results to JSON files and
    copies the relevant service logs.

    :param suite_id: The unique identifier for the test suite.
    :type suite_id: str
    :param suite_state: The state data of the suite.
    :type suite_state: dict
    :param suite_result: The result data of the suite.
    :type suite_result: dict
    :param job_id: The job ID. Defaults to 'latest'.
    :type job_id: str or None
    :return: True if successful, False otherwise.
    :rtype: bool
    """
    try:
        if not job_id:
            job_id = "latest"
        suite_dir = os.path.join(
            data_dir.get_job_data_dir(), job_id, "test_results", suite_id
        )
        os.makedirs(suite_dir, exist_ok=True)

        state_file = os.path.join(suite_dir, "state.json")
        with open(state_file, "w") as f:
            json.dump(suite_state, f, indent=4)

        result_file = os.path.join(suite_dir, "result.json")
        with open(result_file, "w") as f:
            json.dump(suite_result, f, indent=4)

        if os.path.exists(data_dir.SERVICE_LOG_FILENAME):
            shutil.copy(data_dir.SERVICE_LOG_FILENAME, suite_dir)

        LOG.info(
            "Successfully saved suite data for job '%s', suite '%s'", job_id, suite_id
        )
        return True
    except (OSError, IOError, TypeError) as e:
        LOG.error(
            "Failed to save suite data for job '%s', suite '%s': %s",
            job_id,
            suite_id,
            e,
        )
        return False


def load_suite_data(suite_id, job_id=None):
    """
    Loads the state and results for a given test suite.

    If no job_id is provided, it defaults to the latest job.

    :param suite_id: The unique identifier for the test suite.
    :type suite_id: str
    :param job_id: The job ID. Defaults to 'latest'.
    :type job_id: str or None
    :return: A dictionary containing 'state' and 'results' data,
             or None if the data cannot be loaded.
    :rtype: dict or None
    """
    if not job_id:
        job_id = "latest"

    try:
        suite_dir = os.path.join(
            data_dir.get_job_data_dir(), job_id, "test_results", suite_id
        )
        state_file = os.path.join(suite_dir, "state.json")
        result_file = os.path.join(suite_dir, "result.json")

        suite_data = {}
        if os.path.exists(state_file):
            with open(state_file, "r") as f:
                suite_data["state"] = json.load(f)
        if os.path.exists(result_file):
            with open(result_file, "r") as f:
                suite_data["results"] = json.load(f)

        LOG.info(
            "Successfully loaded suite data for job '%s', suite '%s'", job_id, suite_id
        )
        return suite_data if suite_data else None
    except (OSError, IOError, json.JSONDecodeError) as e:
        LOG.error(
            "Failed to load suite data for job '%s', suite '%s': %s",
            job_id,
            suite_id,
            e,
        )
        return None


def delete_suite_data(suite_id, job_id=None):
    """
    Deletes the data directory for a given test suite.

    If no job_id is provided, it defaults to the latest job.

    :param suite_id: The unique identifier for the test suite.
    :type suite_id: str
    :param job_id: The job ID. Defaults to 'latest'.
    :type job_id: str or None
    :return: True if the directory was deleted successfully, False otherwise.
    :rtype: bool
    """
    if not job_id:
        job_id = "latest"

    try:
        suite_dir = os.path.join(
            data_dir.get_job_data_dir(), job_id, "test_results", suite_id
        )
        if os.path.isdir(suite_dir):
            shutil.rmtree(suite_dir)
            LOG.info(
                "Successfully deleted suite data for job '%s', suite '%s'",
                job_id,
                suite_id,
            )
            return True
        else:
            LOG.warning(
                "No data directory found for job '%s', suite '%s'", job_id, suite_id
            )
            return False
    except (OSError, IOError) as e:
        LOG.error(
            "Failed to delete suite data for job '%s', suite '%s': %s",
            job_id,
            suite_id,
            e,
        )
        return False
