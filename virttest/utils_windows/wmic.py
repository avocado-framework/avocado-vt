"""
WMIC utility functions
"""

import re


def noinstance(data):
    """
    Check if the given wmic data contains instance(s).

    :param data: The given wmic data.

    :return: True if no instance(s), else False.
    """
    return bool(re.match("No Instance(s) Available", data.strip(), re.I))


def parse_list(data):
    """
    Parse the given list format wmic data.

    :param data: The given wmic data.

    :return: A list of formated data.
    """
    out = []
    if not noinstance(data):
        for para in re.split("(?:\r?\n){2,}", data.strip()):
            item = {}
            for line in para.splitlines():
                key, value = line.split('=', 1)
                item[key] = value
            out.append(item)
    return out
