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

"""Module that helps string handlings"""

import re


def strip_console_codes(output, custom_codes=None):
    """
    Remove the Linux console escape and control sequences from the console
    output. Make the output readable and can be used for result check. Now
    only remove some basic console codes using during boot up.

    :param output: The output from Linux console
    :type output: string
    :param custom_codes: The codes added to the console codes which is not
                         covered in the default codes
    :type output: string
    :return: the string without any special codes
    :rtype: string
    """
    if "\x1b" not in output:
        return output

    old_word = ""
    return_str = ""
    index = 0
    output = "\x1b[m%s" % output
    console_codes = "%[G@8]|\\[[@A-HJ-MPXa-hl-nqrsu\\`]"
    console_codes += "|\\[[\\d;]+[HJKgqnrm]|#8|\\([B0UK]|\\)"
    if custom_codes is not None and custom_codes not in console_codes:
        console_codes += "|%s" % custom_codes
    while index < len(output):
        tmp_index = 0
        tmp_word = ""
        while (len(re.findall("\x1b", tmp_word)) < 2 and
               index + tmp_index < len(output)):
            tmp_word += output[index + tmp_index]
            tmp_index += 1

        tmp_word = re.sub("\x1b", "", tmp_word)
        index += len(tmp_word) + 1
        if tmp_word == old_word:
            continue
        try:
            special_code = re.findall(console_codes, tmp_word)[0]
        except IndexError as error:
            if index + tmp_index < len(output):
                raise ValueError("%s is not included in the known console "
                                 "codes list %s" % (tmp_word, console_codes)) from error
            continue
        if special_code == tmp_word:
            continue
        old_word = tmp_word
        return_str += tmp_word[len(special_code):]
    return return_str
