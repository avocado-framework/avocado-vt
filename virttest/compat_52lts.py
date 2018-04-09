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
# Copyright: Red Hat Inc. 2018
# Author: Lukas Doktor <ldoktor@redhat.com>

"""
This module contains helpers that allows running Avocado-vt with Avocado
master as well as with 52.x LTS release.
"""


def results_stdout_52lts(result):
    """
    Get decoded stdout text in 52.x LTS backward compatible way

    :param result: result object
    """
    if hasattr(result, "stdout_text"):
        return result.stdout_text
    else:   # 52lts stores string
        return result.stdout


def results_stderr_52lts(result):
    """
    Get decoded stderr text in 52.x LTS backward compatible way

    :param result: result object
    """
    if hasattr(result, "stderr_text"):
        return result.stderr_text
    else:   # 52lts stores string
        return result.stderr
