import operator
import re
from distutils.version import LooseVersion  # pylint: disable=no-name-in-module,import-error


class VersionInterval(object):
    """
    A class for a Version Interval object.

    An interval is a string representation of a mathematical like interval.
    e.g: "(3,4]", "[3.10.0,)"
    A verison is a version string.

    Examples::
        >>> verison_interval = VersionInterval("[2.10.1, 2.11.0)")
        >>> verison = "2.10.16"
        >>> verison in verison_interval
        True
        >>> verison = "2.13.0"
        >>> verison in verison_interval
        False

    """

    def __init__(self, interval):
        interval_rex = r"^(\[|\()(.*?)\s*,\s*(.*?)(\]|\))$"
        match = re.search(interval_rex, interval)
        if match is None:
            raise ValueError("Invalid string representation of an interval")
        self.opening, lower, upper, self.closing = match.groups()

        self.lower_bound = LooseVersion(lower) if lower else None
        self.upper_bound = LooseVersion(upper) if upper else None
        self._check_interval()

    def _check_interval(self):
        if not (self.upper_bound and self.lower_bound):
            return
        if self.lower_bound < self.upper_bound:
            return
        if (self.lower_bound == self.upper_bound and self.opening == '[' and
                self.closing == ']'):
            return
        raise ValueError("Invalid interval")

    def __repr__(self):
        return '<version interval %s%s, %s%s>' % (self.opening,
                                                  self.lower_bound,
                                                  self.upper_bound,
                                                  self.closing)

    def __contains__(self, version):
        op_mapping = {"(": operator.lt, "[": operator.le,
                      ")": operator.gt, "]": operator.ge}
        in_interval = True
        version = LooseVersion(version)
        if self.lower_bound:
            opt = op_mapping.get(self.opening)
            in_interval = opt(self.lower_bound, version)
        if in_interval and self.upper_bound:
            opt = op_mapping.get(self.closing)
            in_interval = opt(self.upper_bound, version)
        return in_interval
