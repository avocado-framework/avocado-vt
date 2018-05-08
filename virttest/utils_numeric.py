from __future__ import division
import math


def align_value(value, factor=1024):
    """
    Value will be factored to the mentioned number.

    :param value: value to be checked or changed to factor
    :param factor: value used for align
    :return: aligned value
    """
    return int(math.ceil(float(value) / factor) * factor)
