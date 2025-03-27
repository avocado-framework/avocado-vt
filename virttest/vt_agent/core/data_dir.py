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
BACKING_MGR_ENV_FILENAME = os.path.join(DATA_DIR, "backing_mgr.env")

AGENT_LOG_FILENAME = os.path.join(LOG_DIR, "agent.log")
SERVICE_LOG_FILENAME = os.path.join(LOG_DIR, "service.log")


LOG = logging.getLogger("avocado.agent" + __name__)


class MissingDirError(Exception):
    pass


def get_root_dir():
    return BASE_DIR


def get_data_dir():
    return DATA_DIR


def get_log_dir():
    return LOG_DIR


def get_download_dir():
    return DOWNLOAD_DIR


def get_tmp_dir(public=True):
    """
    Get the most appropriate tmp dir location.

    :param public: If public for all users' access
    """
    tmp_dir = tempfile.mkdtemp(prefix="agent_tmp_", dir=get_data_dir())
    if public:
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
    return tmp_dir


def get_service_module_dir():
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
    print("service module dir:         " + get_service_module_dir())
    print("download dir:         " + get_download_dir())
    print("tmp dir:          " + get_tmp_dir())
