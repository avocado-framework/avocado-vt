import re
from distutils.version import LooseVersion  # pylint: disable=no-name-in-module,import-error


class VersionInterval(object):
    """
    A class for a Version Interval object.

    An interval is a string representation of a mathmetical like interval.
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
            raise ValueError("Invaild string representation of an interval")
        self.opening, lower, upper, self.closing = match.groups()

        self.lower_bound = LooseVersion(lower) if lower else LooseVersion("0")
        self.upper_bound = LooseVersion(upper) if upper else LooseVersion("z")
        if self.lower_bound > self.upper_bound:
            raise ValueError("Invaild interval")

    def __repr__(self):
        return '<version interval %s%s, %s%s>' % (self.opening,
                                                  self.lower_bound,
                                                  self.upper_bound,
                                                  self.closing)

    def __contains__(self, version):
        version = LooseVersion(version)
        if self.lower_bound < version < self.upper_bound:
            return True
        if version == self.lower_bound:
            return (self.opening == '[')
        if version == self.upper_bound:
            return (self.closing == ']')
