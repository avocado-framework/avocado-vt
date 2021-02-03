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

"""Module intended for various data processors"""

import random
import string

_RAND_POOL = random.SystemRandom()


def generate_random_string(length, ignore=string.punctuation,
                           convert=""):
    """
    Generate a random string using alphanumeric characters.

    :param length: Length of the string that will be generated.
    :type length: int
    :param ignore: Characters that will not include in generated string.
    :type ignore: str
    :param convert: Characters that need to be escaped (prepend "\\").
    :type convert: str

    :return: The generated random string.
    """
    result = ""
    chars = string.ascii_letters + string.digits + string.punctuation
    if not ignore:
        ignore = ""
    for i in ignore:
        chars = chars.replace(i, "")

    while length > 0:
        tmp = _RAND_POOL.choice(chars)
        if convert and (tmp in convert):
            tmp = "\\%s" % tmp
        result += tmp
        length -= 1
    return result
