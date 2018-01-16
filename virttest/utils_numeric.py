import math


def align_factor(value, factor=1024):
    """
    Value will be factored to the mentioned number.

    :param value: value to be checked or changed to factor
    :param factor: value used for align
    :return: factored value
    """
    return int(math.ceil(float(value) / factor) * factor)
