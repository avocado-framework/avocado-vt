import os
import logging
import shutil

from vt_agent.core import data_dir
from virttest import utils_misc

LOG = logging.getLogger("avocado.service." + __name__)


def get_code_info(firmware_path, code_filename):
    code_info = {}
    if not os.path.exists(firmware_path):
        raise ValueError(
            "The firmware path is not exist."
            " Maybe you need to install "
            "related packages."
        )
    code_path = os.path.join(firmware_path, code_filename)
    code_format = utils_misc.get_image_info(code_path)["format"]
    code_info["path"] = code_path
    code_info["format"] = code_format

    return code_info


def get_vars_info(firmware_path, vars_filename):
    vars_info = {}
    if not os.path.exists(firmware_path):
        raise ValueError(
            "The firmware path is not exist."
            " Maybe you need to install "
            "related packages."
        )
    vars_path = os.path.join(firmware_path, vars_filename)
    vars_format = utils_misc.get_image_info(vars_path)["format"]
    vars_info["path"] = vars_path
    vars_info["format"] = vars_format

    return vars_info


def is_vars_path_valid(vars_path):
    if not os.path.isabs(vars_path):
        vars_path = os.path.join(data_dir.get_data_dir(), vars_path)
    return os.path.exists(vars_path)


def restore_vars(vars_src_path, vars_dest_path):
    shutil.copy2(vars_src_path, vars_dest_path)
