import re
import math


def align_factor(value, factor=1024):
    """
    Value will be factored to the mentioned number.

    :param value: value to be checked or changed to factor
    :param factor: value used for align
    :return: factored value
    """
    return int(math.ceil(float(value) / factor) * factor)


class Interval(object):

    """A class for a mathematical interval like object."""

    def __init__(self, interval, data_type):
        interval_re = r"(\[|\()(.*?)\s*,\s*(.*?)(\]|\))"
        match = re.match(interval_re, interval)
        if match is None:
            raise ValueError("Invaild string representation of an interval.")

        self.opening, lower, upper, self.closing = match.groups()
        if not (lower or upper):
            raise ValueError("Invaild interval.")

        self.lower_bound = data_type(lower) if lower else None
        self.upper_bound = data_type(upper) if upper else None
        if lower and upper and (self.lower_bound > self.upper_bound):
            raise ValueError("Invaild interval.")

    def __repr__(self):
        return '<interval %s%s, %s%s>' % (self.opening,
                                          self.lower_bound,
                                          self.upper_bound,
                                          self.closing)

    def __contains__(self, data):
        if self.lower_bound and data < self.lower_bound:
            return False
        if self.upper_bound and data > self.upper_bound:
            return False
        if self.lower_bound and data == self.lower_bound:
            return (self.opening == '[')
        if self.upper_bound and data == self.upper_bound:
            return (self.closing == ']')
        return True

