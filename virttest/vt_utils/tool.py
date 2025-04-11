# Library for the utils tool related functions.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; specifically version 2 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#
# See LICENSE for more details.
#
# Copyright: Red Hat (c) 2024 and Avocado contributors
# Author: Houqi Zuo <hzuo@redhat.com>
import hashlib
import uuid


def ieee_eui_generator(base, mask, start=0, repeat=False):
    """
    IEEE extended unique identifier(EUI) generator.

    :param base: The base identifier number.
    :type base: Integer.
    :param mask: The mask to calculate identifiers.
    :type mask: Integer.
    :param start: The ordinal number of the first identifier.
    :type start: Integer.
    :param repeat: Whether use repeated identifiers when exhausted.
    :type repeat: Boolean.

    :return generator: The target EUI generator.
    :rtype: Iterator.
    """
    offset = 0
    while True:
        out = base + ((start + offset) & mask)
        yield out
        offset += 1
        if offset > mask:
            if not repeat:
                break
            offset = 0


def ieee_eui_assignment(eui_bits):
    """
    IEEE EUI assignment.

    :param eui_bits: The number of EUI bits.
    :type eui_bits: Integer.

    :return: Function object.
    :rtype: Function object.
    """

    def assignment(oui_bits, prefix=0, repeat=False):
        """
        The template of assignment.

        :param oui_bits: The number of OUI bits.
        :type oui_bits: Integer.
        :param prefix: The prefix of OUI, for example 0x9a.
        :type prefix: Integer.
        :param repeat: Whether use repeated identifiers when exhausted.
        :type repeat: Boolean.

        :return: Iterator.
        :rtype: Iterator.
        """
        # Using UUID1 combine with `__file__` to avoid getting the same hash
        data = uuid.uuid1().hex + __file__
        data = hashlib.sha256(data.encode()).digest()[: (eui_bits // 8)]
        sample = 0
        for num in bytearray(data):
            sample <<= 8
            sample |= num
        bits = eui_bits - oui_bits
        mask = (1 << bits) - 1
        start = sample & mask
        base = sample ^ start
        if prefix > 0:
            pbits = eui_bits + (-(prefix.bit_length()) // 4) * 4
            pmask = (1 << pbits) - 1
            prefix <<= pbits
            base = prefix | (base & pmask)
        return ieee_eui_generator(base, mask, start, repeat=repeat)

    return assignment
