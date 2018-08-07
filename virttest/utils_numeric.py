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


def format_size_human_readable(value, binary=False, precision='%.2f'):
    """
    Format a number of bytesize to a human readable filesize. By default,
    decimal suffixes and base:10**3 will be used.

    :param binary: use binary suffixes (KiB, MiB) and use 2*10 as base
    :param precision: format string to specify precision for float
    """

    suffixes = {
        'decimal': ('B', 'kB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB'),
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
