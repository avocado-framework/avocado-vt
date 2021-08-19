"""
Windows WMIC utilities
"""

import re


_WMIC_CMD = "wmic"

FMT_TYPE_LIST = "/format:list"


def make_query(cmd, cond=None, props=None, get_swch=None, gbl_swch=None):
    """
    Make a WMIC query command. The command pattern is:

      wmic [GBL_SWCH] CMD [where COND] get [PROPS] [GET_SWCH]

    :param cmd: WMIC command.
    :param cond: Query condition to be appended to `where`.
    :param props: Properties to be get.
    :param get_swch: Local switch of `get`.
    :param gbl_swch: Global switch.

    :return: Query command.
    """
    query = [_WMIC_CMD, cmd]
    if gbl_swch:
        query.append(gbl_swch)
    if cond:
        query.append("where (%s)" % cond)
    query.append("get")
    if props:
        query.append(",".join(props))
    if get_swch:
        query.append(get_swch)
    return " ".join(query)


def is_noinstance(data):
    """
    Check if the given WMIC data contains instance(s).

    :param data: The given WMIC data.

    :return: True if no instance(s), else False.
    """
    return bool(re.match(r"No Instance\(s\) Available", data.strip(), re.I))


def parse_list(data):
    """
    Parse the given list format WMIC data.

    :param data: The given WMIC data.

    :return: Formatted data.
    """
    out = []
    if not is_noinstance(data):
        for para in re.split("(?:\r?\n){2,}", data.strip()):
            keys, vals = [], []
            for line in para.splitlines():
                key, val = line.split('=', 1)
                keys.append(key)
                vals.append(val)
            if len(keys) == 1:
                out.append(vals[0])
            else:
                out.append(dict(zip(keys, vals)))
    return out
