from __future__ import division
import re
import math
from decimal import Decimal
from decimal import getcontext


def align_value(value, factor=1024):
    """
    Value will be factored to the mentioned number.

    :param value: value to be checked or changed to factor
    :param factor: value used for align
    :return: aligned value
    """
    return int(math.ceil(float(value) / factor) * factor)


def format_size_human_readable(value, binary=False, precision='%.2f'):
    """
    Format a number of bytesize to a human readable filesize.

    By default,decimal suffixes and base:10**3 will be used.
    :param binary: use binary suffixes (KiB, MiB) and use 2*10 as base
    :param precision: format string to specify precision for float
    """
    suffixes = {
        'decimal': ('B', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB'),
        'binary': ('B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB', 'EiB', 'ZiB', 'YiB')
    }
    suffix = suffixes['binary'] if binary else suffixes['decimal']
    base = 1024 if binary else 1000

    value = float(value)
    for i, s in enumerate(suffix):
        unit = base ** (i + 1)
        if value < unit:
            break
    value = value * base / unit
    format_str = ('%d' if value.is_integer() else precision) + ' %s'
    return format_str % (value, s)


def normalize_data_size(value_str, order_magnitude="M", factor=1024):
    """
    Normalize a data size in one order of magnitude to another.

    :param value_str: a string include the data default unit is 'B'
    :param order_magnitude: the magnitude order of result
    :param factor: int, the factor between two relative order of magnitude.
                   Normally could be 1024 or 1000
    :return normalized data size string
    """
    def _get_unit_index(m):
        try:
            return ['B', 'K', 'M', 'G', 'T', 'P', 'E', 'Z', 'Y'].index(
                m.upper())
        except ValueError:
            pass
        return 0

    def _trim_tailling_zeros(num_str):
        # remove tailing zeros, convert float number str to int str
        if '.' in num_str:
            num_str = num_str.rstrip('0').rstrip('.')
        return num_str

    regex = r"(\d+\.?\d*)\s*(\w?)"
    match = re.search(regex, value_str)
    try:
        value = match.group(1)
        unit = match.group(2)
        if not unit:
            unit = 'B'
    except TypeError:
        raise ValueError("Invalid data size format 'value_str=%s'" % value_str)

    getcontext().prec = 20
    from_index = _get_unit_index(unit)
    to_index = _get_unit_index(order_magnitude)
    if from_index - to_index >= 0:
        d = Decimal(value) * Decimal(factor ** (from_index - to_index))
    else:
        d = Decimal(value) / Decimal(factor ** (to_index - from_index))
    return _trim_tailling_zeros('{:f}'.format(d))
