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
import locale

from six import string_types


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


def decode_to_text(stream, encoding=locale.getpreferredencoding(),
                   errors='strict'):
    """
    Decode decoding string
    :param stream: string stream
    :param encoding: encode_type
    :param errors: error handling to use while decoding (strict,replace,
                   ignore,...)
    :return: encoding text
    """
    if hasattr(stream, 'decode'):
        return stream.decode(encoding, errors)
    if isinstance(stream, string_types):
        return stream
    raise TypeError("Unable to decode stream into a string-like type")
